import telnetlib

HOST = "127.0.0.1"
PORT = 5038
USERNAME = "hx"
PASSWORD = "123"  

FROM = "6001"
TO = "6002"
MESSAGE = "Hello from Python"

tn = telnetlib.Telnet(HOST, PORT)
tn.read_until(b"Asterisk Call Manager/")

# Login
tn.write(b"Action: Login\n")
tn.write(b"Username: " + USERNAME.encode() + b"\n")
tn.write(b"Secret: " + PASSWORD.encode() + b"\n")
tn.write(b"\n")

# Send Message
tn.write(b"Action: MessageSend\n")
tn.write(b"To: pjsip:" + TO.encode() + b"\n")
tn.write(b"From: pjsip:" + FROM.encode() + b"\n")
tn.write(b"Body: " + MESSAGE.encode() + b"\n")
tn.write(b"\n")

# Logout
tn.write(b"Action: Logoff\n\n")

# Output
print(tn.read_all().decode())

