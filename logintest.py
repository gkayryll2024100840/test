import hashlib
import secrets
import pymysql


connection = pymysql.connect(
    host="mysql-32679f9d-jillianysabelruedarueda-0f46.f.aivencloud.com",
    port=25535,
    user="avnadmin",
    password="AVNS_0YehvvEeTs4w4hWFIDg",  
    database="defaultdb",
    charset="utf8mb4"
)

# Hash the password
password = "password123"
salt = secrets.token_hex(16)
password_hash = hashlib.sha256((password + salt).encode()).hexdigest()

try:
    with connection.cursor() as cursor:
        # Insert placheholder
        sql = """
            INSERT INTO Users (UserID, FirstName, LastName, password_hash, salt, role, email)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            FirstName = VALUES(FirstName),
            LastName = VALUES(LastName),
            password_hash = VALUES(password_hash),
            salt = VALUES(salt),
            role = VALUES(role),
            email = VALUES(email)
        """
        
        cursor.execute(sql, (
            "2024-10012",
            "Juan",
            "dela Cruz",
            password_hash,
            salt,
            "Faculty_Advisor",
            "juandelacruz@gmail.com"
        ))
        
        connection.commit()
        print("Juan dela Cruz inserted/updated successfully!")
        print(f"Username: 2024-10012")
        print(f"Password: password123")
        
except pymysql.Error as e:
    print(f"❌ Error: {e}")
    connection.rollback()
finally:
    connection.close()