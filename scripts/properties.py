class Properties:

    def __init__(self, filepath):

        self.properties = {}
        self.filepath = filepath
        
        file = open(self.filepath, 'r')
        for line in file.readlines():
            
            line = line.strip()
            if not line or line.startswith("#"): continue
            
            key_value = line.split("=")
            key = key_value[0].strip()
            value = "=".join(key_value[1:]).strip('"')

            if   value.lower() == 'true':  value = True
            elif value.lower() == 'false': value = False
            elif value.isnumeric(): value = int(value)

            self.properties[key] = value

        file.close()

    def __getitem__(self, key):
        return self.properties[key]

    def __setitem__(self, key, new_value):
        self.properties[key] = new_value

    def write(self):

        file = open(self.filepath, 'w')
        file.write('#Minecraft server starter properties\n')

        for key in sorted(self.properties.keys()): 
            if type(self.properties[key]) == bool and self.properties[key] == True:  file.write(f'{key}=true\n')
            if type(self.properties[key]) == bool and self.properties[key] == False: file.write(f'{key}=false\n')
            else: file.write(f'{key}={self.properties[key]}\n')

        file.close()