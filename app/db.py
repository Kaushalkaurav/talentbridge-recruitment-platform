import os, sqlite3, secrets, hashlib, hmac, datetime
from contextlib import contextmanager
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DB_FILE=Path(os.environ.get('TALENTBRIDGE_DB',str(ROOT/'data'/'talentbridge.sqlite3')))
DB_FILE.parent.mkdir(parents=True, exist_ok=True)

def utc(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
@contextmanager
def db():
    c=sqlite3.connect(DB_FILE,timeout=15)
    c.row_factory=sqlite3.Row
    c.execute('pragma foreign_keys=on')
    c.execute('pragma busy_timeout=15000')
    try:
        yield c
        c.commit()
    except:
        c.rollback();raise
    finally:c.close()

def init_db():
    with db() as c:
        c.executescript('''
        create table if not exists users(id integer primary key, name text not null, email text not null unique, phone text default '', role text not null check(role in ('admin','employer','candidate')), pw_hash text not null, company text default '', created_at text not null);
        create table if not exists sessions(id_hash text primary key,user_id integer not null references users(id) on delete cascade, csrf text not null,expires_at integer not null);
        create table if not exists candidates(id integer primary key, user_id integer unique not null references users(id) on delete cascade, location text not null, experience text not null, skills text not null, preferred_role text not null, consent integer not null check(consent in (0,1)), consent_at text not null, resume_id integer, status text not null default 'new', created_at text not null);
        create table if not exists employer_enquiries(id integer primary key,user_id integer not null references users(id),company_name text not null,contact_person text not null,email text not null,phone text not null,job_role text not null,openings integer not null check(openings>0),location text not null,description text not null,status text not null default 'new',document_id integer,created_at text not null);
        create table if not exists documents(id integer primary key,owner_user_id integer not null references users(id),kind text not null check(kind in ('resume','jd')),storage_name text not null unique,original_name text not null,mime text not null,created_at text not null);
        create table if not exists jobs(id integer primary key,title text not null,company text not null,location text not null,category text not null,description text not null,employment_type text not null default 'Full-time',published integer not null default 0,created_by integer not null references users(id),created_at text not null);
        create table if not exists applications(id integer primary key,job_id integer not null references jobs(id),candidate_id integer not null references users(id),status text not null default 'applied',created_at text not null, unique(job_id,candidate_id));
        create table if not exists contacts(id integer primary key,name text not null,email text not null,phone text not null default '',message text not null,status text not null default 'new',created_at text not null);
        create table if not exists activity_log(id integer primary key,admin_user_id integer not null references users(id),entity text not null,entity_id integer not null,action text not null,created_at text not null);
        create index if not exists idx_candidates_skills on candidates(skills);
        create index if not exists idx_employer_user on employer_enquiries(user_id);
        create index if not exists idx_applications_candidate on applications(candidate_id);
        ''')

def pw_hash(password):
    salt=secrets.token_bytes(16)
    key=hashlib.scrypt(password.encode(),salt=salt,n=2**14,r=8,p=1)
    return salt.hex()+':'+key.hex()
def verify_pw(password,encoded):
    try:
        a,b=encoded.split(':',1);actual=hashlib.scrypt(password.encode(),salt=bytes.fromhex(a),n=2**14,r=8,p=1)
        return hmac.compare_digest(actual,bytes.fromhex(b))
    except (ValueError,TypeError):return False
