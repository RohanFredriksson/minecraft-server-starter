import java.io.*;
import java.net.*;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.Properties;

/**
 * Stand-in for the vanilla Minecraft server used by the tests.
 *
 * It prints the console lines the starter watches for, binds the port from server.properties
 * through NIO like the real server does, and implements just enough of the protocol to answer
 * status requests and to accept a login.
 *
 * Usage: java FakeServer.java [normal|slow|crash]
 */
public class FakeServer {

    static final DateTimeFormatter TIME = DateTimeFormatter.ofPattern("HH:mm:ss");

    public static void main(String[] args) throws Exception {

        String mode = args.length > 0 ? args[0] : "normal";

        Properties properties = new Properties();
        try (Reader reader = new FileReader("server.properties")) { properties.load(reader); }
        String ip = properties.getProperty("server-ip", "").trim();
        int port = Integer.parseInt(properties.getProperty("server-port", "25565").trim());

        Thread.sleep(mode.equals("slow") ? 6000 : 500);
        log("INFO", "Starting minecraft server version Fake");

        if (mode.equals("crash")) {
            log("ERROR", "Encountered an unexpected exception");
            System.exit(1);
        }

        // The real server binds about 50-120 ms after this line.
        Thread.sleep(50);
        log("INFO", "Starting Minecraft server on " + (ip.isEmpty() ? "*" : ip) + ":" + port);

        ServerSocketChannel listener = ServerSocketChannel.open();
        try {
            listener.bind(ip.isEmpty() ? new InetSocketAddress(port) : new InetSocketAddress(ip, port));
        } catch (IOException error) {
            log("WARN", "**** FAILED TO BIND TO PORT!");
            log("WARN", "The exception was: " + error);
            System.exit(1);
        }

        Thread acceptor = new Thread(() -> {
            while (true) {
                try {
                    SocketChannel channel = listener.accept();
                    Thread handler = new Thread(() -> handle(channel.socket()));
                    handler.setDaemon(true);
                    handler.start();
                } catch (IOException error) {
                    return;
                }
            }
        });
        acceptor.setDaemon(true);
        acceptor.start();

        Thread.sleep(300);
        log("INFO", "Done (0.350s)! For help, type \"help\"");

        BufferedReader console = new BufferedReader(new InputStreamReader(System.in));
        while (true) {
            String line = console.readLine();
            if (line == null || line.trim().equals("stop")) break;
        }

        log("INFO", "Stopping server");
        listener.close();
        System.exit(0);
    }

    static void log(String level, String message) {
        System.out.println("[" + LocalTime.now().format(TIME) + "] [Server thread/" + level + "]: " + message);
        System.out.flush();
    }

    static void handle(Socket socket) {
        try (socket) {
            socket.setSoTimeout(10000);
            DataInputStream in = new DataInputStream(new BufferedInputStream(socket.getInputStream()));
            OutputStream out = socket.getOutputStream();

            DataInputStream handshake = readPacket(in, 0x00);
            readVarInt(handshake);
            readString(handshake);
            handshake.readUnsignedShort();
            int next = readVarInt(handshake);

            if (next == 1) {
                readPacket(in, 0x00);
                String status = "{\"version\":{\"name\":\"Fake\",\"protocol\":767},"
                    + "\"players\":{\"max\":20,\"online\":0,\"sample\":[]},"
                    + "\"description\":{\"text\":\"Fake server\"}}";
                writePacket(out, 0x00, string(status));
                DataInputStream ping = readPacket(in, 0x01);
                byte[] payload = new byte[8];
                ping.readFully(payload);
                writePacket(out, 0x01, payload);
                return;
            }

            // Login success, then expect the client's acknowledgement. Anything else means the
            // starter forwarded something the real server would not expect.
            DataInputStream login = readPacket(in, 0x00);
            String name = readString(login);
            byte[] uuid = new byte[16];
            login.readFully(uuid);

            ByteArrayOutputStream success = new ByteArrayOutputStream();
            success.write(uuid);
            success.write(string(name));
            success.write(varInt(0));
            writePacket(out, 0x02, success.toByteArray());

            int id = readVarInt(new DataInputStream(new ByteArrayInputStream(readFrame(in))));
            String reply = id == 0x03 ? "Welcome " + name : "Unexpected packet 0x" + Integer.toHexString(id);
            writePacket(out, 0x00, string("{\"text\":\"" + reply + "\"}"));

        } catch (IOException error) {
            // Clients are allowed to disconnect at any time.
        }
    }

    static byte[] readFrame(DataInputStream in) throws IOException {
        byte[] frame = new byte[readVarInt(in)];
        in.readFully(frame);
        return frame;
    }

    static DataInputStream readPacket(DataInputStream in, int expected) throws IOException {
        DataInputStream packet = new DataInputStream(new ByteArrayInputStream(readFrame(in)));
        int id = readVarInt(packet);
        if (id != expected) throw new IOException("Unexpected packet 0x" + Integer.toHexString(id));
        return packet;
    }

    static void writePacket(OutputStream out, int id, byte[] payload) throws IOException {
        ByteArrayOutputStream body = new ByteArrayOutputStream();
        body.write(varInt(id));
        body.write(payload);
        ByteArrayOutputStream frame = new ByteArrayOutputStream();
        frame.write(varInt(body.size()));
        body.writeTo(frame);
        out.write(frame.toByteArray());
        out.flush();
    }

    static int readVarInt(DataInputStream in) throws IOException {
        int value = 0;
        for (int shift = 0; shift < 35; shift += 7) {
            int current = in.readUnsignedByte();
            value |= (current & 0x7F) << shift;
            if ((current & 0x80) == 0) return value;
        }
        throw new IOException("VarInt is too big");
    }

    static String readString(DataInputStream in) throws IOException {
        byte[] bytes = new byte[readVarInt(in)];
        in.readFully(bytes);
        return new String(bytes, StandardCharsets.UTF_8);
    }

    static byte[] varInt(int value) {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        while ((value & ~0x7F) != 0) {
            out.write((value & 0x7F) | 0x80);
            value >>>= 7;
        }
        out.write(value);
        return out.toByteArray();
    }

    static byte[] string(String text) throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        out.write(varInt(bytes.length));
        out.write(bytes);
        return out.toByteArray();
    }
}
