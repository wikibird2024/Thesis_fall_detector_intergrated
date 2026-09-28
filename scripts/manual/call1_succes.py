import telnetlib

def originate_call(host, port, user, secret, caller, exten, context="internal"):
    try:
        tn = telnetlib.Telnet(host, port)
        tn.read_until(b"Asterisk Call Manager")

        # Login
        tn.write(b"Action: Login\n")
        tn.write(f"Username: {user}\n".encode())
        tn.write(f"Secret: {secret}\n\n".encode())
        tn.read_until(b"Message: Authentication accepted", timeout=2)

        # Originate call
        tn.write(b"Action: Originate\n")
        tn.write(f"Channel: PJSIP/{caller}\n".encode())
        tn.write(f"Context: {context}\n".encode())
        tn.write(f"Exten: {exten}\n".encode())
        tn.write(b"Priority: 1\n")
        tn.write(b"CallerID: AMI Test <100>\n")
        tn.write(b"Timeout: 30000\n\n")

        # Logoff
        tn.write(b"Action: Logoff\n\n")
        output = tn.read_all().decode()

        return output
    except Exception as e:
        return f"Error: {e}"

# Gọi hàm
output = originate_call(
    host="127.0.0.1",
    port=5038,
    user="hx",
    secret="123",
    caller="6001",
    exten="6002"
)

print(output)

