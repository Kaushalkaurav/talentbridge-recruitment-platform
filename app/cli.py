import sys,getpass
from .db import init_db,db,pw_hash,utc

def main():
    if len(sys.argv)<2 or sys.argv[1]!='create-admin':
        print('Usage: python -m app.cli create-admin');return
    init_db()
    name=input('Admin name: ').strip();email=input('Admin email: ').strip().lower();password=getpass.getpass('Admin password (10+ chars): ')
    if len(password)<10 or not name or '@' not in email:raise SystemExit('Invalid admin details')
    with db() as c:
        try:c.execute('insert into users(name,email,role,pw_hash,created_at) values(?,?,?,?,?)',(name,email,'admin',pw_hash(password),utc()))
        except Exception as e:raise SystemExit('Could not create admin: '+str(e))
    print('Admin created. Sign in at /login.')
if __name__=='__main__':main()
