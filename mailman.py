import smtplib
import imaplib
import email
import sys, os
from datetime import *

"""mailman is a drop in solution for sending and receiving email
deliver() is used to send the mail and requires a dictionary with the following
keys to be passed

config = {"sender":"example1@gmail.com", 
          "recipient":"example2@gmail.com",
          "mail_enabled": True,
          "smtp_server": "smtp.gmail.com",
          "smtp_port": 587,
          "username":"example1@gmail.com",
          "password":"password"}

Gmail Note: To avoid temporarily locking yourself out of your account, 
make sure you don't exceed 2500 MB per day for IMAP downloads and 
500 MB per day for IMAP uploads. 



collect() is used to grab the body of an email for further parsing.
requires a dictionary with the following keys to be passed

config = {"mail_enabled": True,
          "imap_server": "imap.gmail.com",
          "imap_port": 993,
          "username":"example1@gmail.com",
          "password":"password"}
"""

sendLog = {}
lastCheck = False


def deliver(config = {}, msg = "Error", frequency = timedelta(minutes=30)):
    global sendLog
    timeout = 10
    try:
        #Don't spam user if error occurs
        if not msg in sendLog or datetime.now() > sendLog[msg]:
            sendLog[msg] = datetime.now() + frequency
            #Create Form (Headers + Message)
            Form = ('From: {sender}\r\n'
                      + 'To: {recipient}\r\n'
                      + 'MIME-Version: 1.0\r\n'
                      + 'Subject: \r\n'
                      + 'Content-Type: multipart/alternative; '
                      + 'boundary="00000000000087da59057f203efd"\r\n'
                      + '--00000000000087da59057f203efd\r\n'
                      + 'Content-Type: text/plain; charset="UTF-8"\r\n'
                      + '{message}\r\n'
                      + '--00000000000087da59057f203efd'
                      + 'Content-Type: text/html; charset="UTF-8"\r\n\r\n'
                      + '<div dir="ltr"><font face="Roboto, RobotoDraft,'
                      + 'Helvetica, Arial"><span style="font-size:12.8px">'
                      + '{message}</span></font></div>'
                      ).format( sender = config['sender'], 
                                recipient = config['recipient'], 
                                message = msg)
            #Create session
            session = smtplib.SMTP(config['smtp_server'], 
                                    config['smtp_port'],
                                    timeout = timeout)
            session.ehlo()
            # comment this out if you're crazy and use non-tls SMTP servers
            session.starttls()
            session.ehlo
            session.login(config['username'], config['password'])
            session.sendmail(config['sender'], config['recipient'], Form)
            session.quit()
            return True, "Yes! The mailman delivered!"
    except smtplib.socket.timeout:
        return False, "mailman.deliver() timed out!"
        #//TODO: SEND STRING TO DAEMON record.DebugLog
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        return False, ("mailman.deliver() had an error:\n{0} {1} {2} {3}"
                        ).format(sys.exc_info()[0],exc_type, 
                                 fname, exc_tb.tb_lineno)
    
    return False, "Message being sent too frequently: {0}".format(msg)
           

def collect(config = {}, frequency = timedelta(seconds=30), markSeen = True):
    global lastCheck
    try:
        if (lastCheck is False or datetime.now() > (lastCheck + frequency)):
            #Connect to imap server
            lastCheck = datetime.now()
            conn = imaplib.IMAP4_SSL(config['imap_server'], config['imap_port'])
            (retcode, capabilities) = conn.login(config['username'], 
                                                 config['password'])
            conn.select("inbox")
            #Only grab unread messages
            (retcode, messages) = conn.search(None, '(UNSEEN)')
            if retcode == 'OK' and messages[0]:
                #iterate through messages
                for num in messages[0].split(' '):
                    #grab data
                    typ, data = conn.fetch(num,'(RFC822)')
                    #get message portion of data
                    msg = email.message_from_string(data[0][1])
                    #set message to seen
                    if markSeen:
                        typ, data = conn.store(num,'+FLAGS','\\Seen')
                    else:
                        typ, data = conn.store(num,'-FLAGS','\\Seen')
                    #find sender & subject
                    sender = email.utils.parseaddr(msg['From'])[1]
                    subject = email.Header.decode_header(msg['Subject'])[0][0]
                    #find body if multipart message
                    if msg.is_multipart():
                        for part in msg.walk():
                            ctype = part.get_content_type()
                            cdispo = str(part.get('Content-Disposition'))

                            # skip any text/plain (txt) attachments
                            if ctype == 'text/plain' and 'attachment' not in cdispo:
                                body = part.get_payload(decode=True)  # decode
                                break
                    # find body if not multipart - (plain text, no attachments)
                    else:
                        body = msg.get_payload(decode=True)
                    
                    yield {"sender": sender, "subject": subject, "body": body}
                conn.close()
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        yield {"sender": "ERROR",
                "subject":"mailman.collect() had an error!",
                "body": ("{0} {1} {2} line: {3}").format(sys.exc_info()[0],exc_type, 
                                                    fname, exc_tb.tb_lineno)}
