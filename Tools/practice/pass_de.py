import base64

def decrypt_pass(password):
    decoded_bytes = base64.b64decode(user_pass)
    print(decoded_bytes)

user_pass = input("enter encrypted password: ")
decrypt_pass(user_pass)
