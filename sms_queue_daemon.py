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
