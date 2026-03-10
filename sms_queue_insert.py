#!/usr/bin/python3.6
import sys
import re
import pymysql

DB = {
    "host": "127.0.0.1",
    "user": "DB_USER",
    "password": "DB_PASSWORD",
    "database": "asterisk",
    "charset": "utf8",
    "autocommit": True
}

def read_env():
    while True:
        line=sys.stdin.readline().strip()
        if line=="":
            break

def agi_cmd(cmd):
    sys.stdout.write(cmd+"\n")
    sys.stdout.flush()
    return sys.stdin.readline()

def getvar(name):
    resp=agi_cmd("GET FULL VARIABLE {}".format(name))
    m=re.search(r'result=1 \((.*)\)',resp)
    if m:
        return m.group(1)
    return ""

read_env()

ext=getvar("${NUMBER_TO}")
src=getvar("${ACTUAL_FROM}")
dst=getvar("${ACTUAL_TO}")
body=getvar("${MSG_BODY}")

conn=pymysql.connect(**DB)
cur=conn.cursor()

cur.execute("""
INSERT INTO sms_queue (ext,src,dst,body,status)
VALUES (%s,%s,%s,%s,'queued')
""",(ext,src,dst,body))

conn.commit()
cur.close()
conn.close()
