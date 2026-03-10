# Voip.ms_SIP-SMS_Queue_FreePBX
Offline SMS Queue for Asterisk 20/ FreePBX 16 (voip.ms)



While using the SIP SMS configuration from your documentation: https://wiki.voip.ms/article/SIP/SMS_with_FreePBX

I noticed that if the SIP endpoint (UE) is not registered when the SMS arrives, Asterisk attempts the MessageSend() but the message is not delivered.

To work around this, I created a small script that stores the SMS in a local queue when the endpoint is offline and automatically retries delivery once the endpoint reconnects.

This solution works on top of the existing configuration from the wiki and does not require changes to the trunk setup.
