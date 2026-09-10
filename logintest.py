import os
import hashlib
import secrets
import pymysql
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error

load_dotenv()
timeout = 10

DB_CONFIG = {
    'charset': "utf8mb4",
    'connect_timeout': 10,
    'cursorclass': pymysql.cursors.DictCursor,
    'database': "defaultdb",
    'host': "mysql-32679f9d-jillianysabelruedarueda-0f46.f.aivencloud.com",
    'password': os.getenv('DB_PASSWORD'),
    'read_timeout': 10,
    'port': 25535,
    'user': "avnadmin",
    'write_timeout': 10,
}

def hash_password(password, salt=None):
    """Hash password using SHA256 with salt"""
    if salt is None:
        salt = secrets.token_hex(16)
    combined = password + salt
    password_hash = hashlib.sha256(combined.encode()).hexdigest()
    return password_hash, salt

def insert_jane_user():
    """Insert Jane Doe as a test user"""
    connection = pymysql.connect(**DB_CONFIG)
    
    try:
        with connection.cursor() as cursor:
            user_id = "1111111111"
            first_name = "Jane"
            last_name = "Doe"
            role = "Dean"
            email = "janedoe@gmail.com"
            plain_password = "password321"

            password_hash, salt = hash_password(plain_password)
            
            sql = """
                    INSERT INTO Users (UserID, FirstName, LastName, password_hash, salt, role, email)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
            cursor.execute(sql, (user_id, first_name, last_name, password_hash, salt, role, email))
            connection.commmit()
            print("Database updated")

    except pymysql.Error as e:
        print(f"❌ Database error: {e}")
        connection.rollback()

    finally:
        connection.close()

if __name__ == "__main__":
    insert_jane_user()