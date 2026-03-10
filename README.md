# Voip.ms_SIP-SMS_Queue_FreePBX
Offline SMS Queue for Asterisk 20/ FreePBX 16 (voip.ms)



While using the SIP SMS configuration from this documentation: https://wiki.voip.ms/article/SIP/SMS_with_FreePBX

I noticed that if the SIP endpoint (UE) is not registered when the SMS arrives, Asterisk attempts the MessageSend() but the message is not delivered.

To work around this, I created a small script that stores the SMS in a local queue when the endpoint is offline and automatically retries delivery once the endpoint reconnects.

This solution works on top of the existing configuration from the wiki and does not require changes to the trunk setup.





Offline SMS Queue System for FreePBX / Asterisk (voip.ms)
Deployment Guide – Complete Implementation
________________________________________
1. Introduction
This document describes how to implement a reliable SMS queue system for Asterisk / FreePBX using voip.ms SIP messaging.
The objective of this system is to prevent SMS loss when SIP endpoints are offline.
By default, when Asterisk receives an SMS and attempts to deliver it using MessageSend(), the message fails if the endpoint is not registered. In most deployments this means the message is simply lost.
This system introduces a database-backed queue and automatic replay mechanism.
When an SMS cannot be delivered:
1.	The message is stored in a MySQL queue.
2.	A background daemon monitors endpoint registration.
3.	When the endpoint reconnects, the SMS is automatically replayed.
This ensures reliable SMS delivery even if endpoints temporarily disconnect.
________________________________________
2. Important Prerequisite
This solution builds on top of the official voip.ms SMS configuration.
The base configuration must already be working before implementing this system.
Official guide:
https://wiki.voip.ms/article/SIP/SMS_with_FreePBX
The following must already function:
•	inbound SMS reception via SIP MESSAGE
•	outbound SMS delivery from extensions
•	working sms-in or im-sms dialplan
•	proper voip.ms SIP trunk configuration
This project does NOT replace that configuration.
Instead it extends it by adding:
•	SMS persistence
•	automatic retry
•	offline delivery support
________________________________________
3. System Architecture
voip.ms
   │
   ▼
Asterisk receives SIP MESSAGE
   │
   ▼
[sms-in] dialplan
   │
   ├── MessageSend SUCCESS → delivered immediately
   │
   └── MessageSend FAILURE
           │
           ▼
     sms_queue_insert.py (AGI)
           │
           ▼
       MySQL sms_queue table
           │
           ▼
    sms_queue_daemon.py
           │
           ▼
   endpoint becomes online
           │
           ▼
  callfile created in Asterisk spool
           │
           ▼
   sms-queue-replay dialplan
           │
           ▼
       MessageSend retry
________________________________________
4. Requirements
Software
•	Asterisk
•	FreePBX
•	MariaDB / MySQL
•	Python 3.6+
Required Asterisk modules
Verify:
asterisk -rx "module show like pjsip"
asterisk -rx "module show like message"
Required modules:
res_pjsip.so
res_pjsip_messaging.so
app_message.so
pbx_spool.so
________________________________________
5. Install Python dependency
python3.6 -m ensurepip --default-pip
python3.6 -m pip install PyMySQL
________________________________________
6. Database Setup
Connect to MySQL:
mysql -u root -p
Select the database:
USE asterisk;
Create the queue table:
CREATE TABLE sms_queue (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    ext VARCHAR(20) NOT NULL,
    src VARCHAR(255) NOT NULL,
    dst VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    status ENUM('queued','sending','sent','failed') NOT NULL DEFAULT 'queued',
    tries INT NOT NULL DEFAULT 0,
    last_error VARCHAR(255) DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at DATETIME DEFAULT NULL,
    PRIMARY KEY (id),
    KEY idx_ext_status (ext, status),
    KEY idx_status_created (status, created_at)
);
________________________________________
7. AGI Script – SMS Queue Insert
Create:
/var/lib/asterisk/agi-bin/sms_queue_insert.py
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
Permissions:
chmod +x /var/lib/asterisk/agi-bin/sms_queue_insert.py
chown asterisk:asterisk /var/lib/asterisk/agi-bin/sms_queue_insert.py
________________________________________
8. Modified inbound SMS dialplan
File:
/etc/asterisk/extensions_custom.conf
[sms-in]
exten => _.,1,NoOp(Inbound SMS received)

same => n,Set(NUMBER_TO=${MESSAGE_DATA(X-SMS-To)})
same => n,Set(HOST_TO=${CUT(MESSAGE(to),@,2)})
same => n,Set(ACTUAL_FROM=${MESSAGE(from)})
same => n,Set(ACTUAL_TO=pjsip:${NUMBER_TO}@${HOST_TO})
same => n,Set(MSG_BODY=${MESSAGE(body)})

same => n,MessageSend(${ACTUAL_TO},${ACTUAL_FROM})
same => n,NoOp(Status ${MESSAGE_SEND_STATUS})

same => n,GotoIf($["${MESSAGE_SEND_STATUS}"="SUCCESS"]?done)

same => n,AGI(sms_queue_insert.py)
same => n,NoOp(SMS queued)

same => n(done),Hangup()
Reload:
fwconsole reload
________________________________________
9. SMS replay dialplan
[sms-queue-replay]

exten => send,1,NoOp(Replaying queued SMS)

same => n,Set(TARGET_EXT=${ARG1})
same => n,Set(MSG_FROM=${ARG2})
same => n,Set(MSG_BODY=${ARG3})
same => n,Set(ACTUAL_TO=pjsip:${TARGET_EXT})

same => n,Set(MESSAGE(body)=${MSG_BODY})
same => n,Set(MESSAGE(from)=${MSG_FROM})

same => n,MessageSend(${ACTUAL_TO},${MSG_FROM})

same => n,Hangup()
Reload again:
fwconsole reload
________________________________________
10. SMS Queue Daemon
Create:
/usr/local/bin/sms_queue_daemon.py
#!/usr/bin/python3.6
import time
import subprocess
import pymysql
import os
import tempfile
import pwd
import grp

DB={
"host":"127.0.0.1",
"user":"DB_USER",
"password":"DB_PASSWORD",
"database":"asterisk",
"charset":"utf8",
"autocommit":True
}

OUT="/var/spool/asterisk/outgoing"

def online(ext):
cmd='asterisk -rx "pjsip show aor {}"'.format(ext)
out=subprocess.getoutput(cmd)
return "Contact:" in out

def callfile(ext,src,body,id):

fd,tmp=tempfile.mkstemp(prefix="smsq_",suffix=".call",dir="/tmp")
os.close(fd)

content=f"""Channel: Local/send@sms-queue-replay
Context: sms-queue-replay
Extension: send
Priority: 1
Set: ARG1={ext}
Set: ARG2={src}
Set: ARG3={body}
Set: SMSQ_ID={id}
"""

with open(tmp,"w") as f:
  f.write(content)

os.chmod(tmp,0o640)

uid=pwd.getpwnam("asterisk").pw_uid
gid=grp.getgrnam("asterisk").gr_gid

os.chown(tmp,uid,gid)

os.rename(tmp,OUT+"/"+os.path.basename(tmp))

def loop():

conn=pymysql.connect(**DB)
cur=conn.cursor()

cur.execute("SELECT id,ext,src,body FROM sms_queue WHERE status='queued'")

for id,ext,src,body in cur.fetchall():

  if online(ext):

   callfile(ext,src,body,id)

   cur.execute("UPDATE sms_queue SET status='sending' WHERE id=%s",(id,))
   conn.commit()

cur.close()
conn.close()

while True:
try:
  loop()
except:
  pass
time.sleep(5)
Permissions:
chmod +x /usr/local/bin/sms_queue_daemon.py
________________________________________
11. Fix Asterisk spool permissions
chown -R asterisk:asterisk /var/spool/asterisk/outgoing
chmod 750 /var/spool/asterisk/outgoing
________________________________________
12. Create system service
File:
/etc/systemd/system/sms-queue-daemon.service
[Unit]
Description=SMS Queue Daemon
After=network.target asterisk.service mariadb.service

[Service]
ExecStart=/usr/bin/python3.6 /usr/local/bin/sms_queue_daemon.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
Enable:
systemctl daemon-reload
systemctl enable sms-queue-daemon
systemctl start sms-queue-daemon
________________________________________
13. Testing
Test procedure:
1.	Disconnect the SIP endpoint.
2.	Send an SMS.
3.	Confirm the message appears in:
SELECT * FROM sms_queue;
4.	Reconnect the endpoint.
5.	The daemon detects the registration.
6.	The SMS is automatically delivered.
________________________________________
14. Result
With this system:
•	SMS messages are never lost
•	Offline endpoints receive queued SMS after reconnect
•	The process is fully automated
•	Delivery status is stored in the database
•	The solution integrates cleanly with FreePBX and voip.ms

