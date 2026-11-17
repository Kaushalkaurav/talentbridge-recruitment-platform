import os, time, secrets, hashlib, re, smtplib, ssl, html, csv, io, zipfile, logging
from pathlib import Path
from collections import defaultdict,deque
from email.message import EmailMessage
from urllib.parse import quote
from markupsafe import Markup, escape
from fastapi import FastAPI, Request
from starlette.datastructures import UploadFile
from fastapi.responses import HTMLResponse,RedirectResponse,FileResponse,PlainTextResponse,StreamingResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from .db import db,init_db,utc,pw_hash,verify_pw,ROOT

app=FastAPI(title='Talent Bridge Recruitment Platform',docs_url=None,redoc_url=None)
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
templates=Environment(loader=FileSystemLoader(ROOT/'templates'),autoescape=select_autoescape(['html']))
def status_form(csrf,kind,item_id,status,choices,tab):
    options=''.join(f'<option value="{escape(x)}" {"selected" if x==status else ""}>{escape(x.replace("_"," ").title())}</option>' for x in choices)
    return Markup(f'<form method="post" action="/admin/status" class="status-form"><input type="hidden" name="csrf" value="{escape(csrf)}"><input type="hidden" name="kind" value="{escape(kind)}"><input type="hidden" name="id" value="{int(item_id)}"><input type="hidden" name="tab" value="{escape(tab)}"><select name="status" aria-label="Update status">{options}</select><button type="submit" class="tiny-button">Save</button></form>')
templates.globals['status_form']=status_form
UPLOAD_DIR=Path(os.environ.get('TALENTBRIDGE_UPLOADS',str(ROOT/'data'/'uploads')))
UPLOAD_DIR.mkdir(parents=True,exist_ok=True)
MAX_UPLOAD=5*1024*1024
STATUS={'candidate':['new','screening','shortlisted','interview','placed','rejected'], 'enquiry':['new','reviewing','in_progress','closed'], 'application':['applied','screening','shortlisted','interview','offered','hired','rejected'], 'contact':['new','responded','closed']}
limit=defaultdict(deque)
logger=logging.getLogger('talentbridge')
MAX_DESCRIPTION=12000

def render(request, template, status=200,**data):
    user=session_user(request)
    token=request.state.csrf if hasattr(request.state,'csrf') else ''
    return HTMLResponse(templates.get_template(template).render(request=request,user=user,csrf=token,preview_mode=os.environ.get('TALENTBRIDGE_PREVIEW_ONLY')=='1',**data),status_code=status)
def go(url):return RedirectResponse(url,status_code=303)
def token_hash(v):return hashlib.sha256(v.encode()).hexdigest()
def session_user(request):
    if hasattr(request.state,'user'):return request.state.user
    return None

def require(request,role=None):
    user=session_user(request)
    if not user: return go('/login?next='+quote(request.url.path))
    if role and user['role']!=role:return PlainTextResponse('Access denied',status_code=403)
    return None

def check_csrf(request,form):
    secret=getattr(request.state,'csrf',None)
    if not secret or not secrets.compare_digest(str(form.get('csrf','')),secret):return False
    return True

def throttle(request,group='form',max_hits=12,window=3600):
    # In-memory best-effort throttle; production should add reverse proxy rate controls.
    key=(request.client.host if request.client else 'unknown',group)
    now=time.monotonic();q=limit[key]
    while q and q[0]<now-window:q.popleft()
    if len(q)>=max_hits:return False
    q.append(now);return True

def normal(value,maxlen=500):return str(value or '').strip()[:maxlen]
def mail_ok(value):return bool(re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',value)) and len(value)<=254

def notification(subject,body):
    host=os.environ.get('SMTP_HOST',''); recipient=os.environ.get('ADMIN_NOTIFICATION_EMAIL','')
    if not host or not recipient:return False
    try:
        message=EmailMessage();message['Subject']=subject;message['From']=os.environ.get('SMTP_FROM',os.environ.get('SMTP_USER',''));message['To']=recipient;message.set_content(body)
        with smtplib.SMTP(host,int(os.environ.get('SMTP_PORT','587')),timeout=10) as smtp:
            smtp.starttls(context=ssl.create_default_context());smtp.login(os.environ.get('SMTP_USER',''),os.environ.get('SMTP_PASSWORD',''));smtp.send_message(message)
        return True
    except Exception as e:
        logger.exception('Email notification failed');return False

def audit(c,user,entity,id,action):c.execute('insert into activity_log(admin_user_id,entity,entity_id,action,created_at) values(?,?,?,?,?)',(user['id'],entity,id,action,utc()))

@app.on_event('startup')
def startup():init_db()

@app.middleware('http')
async def protect(request,call_next):
    if os.environ.get('TALENTBRIDGE_PREVIEW_ONLY')=='1' and request.method not in ('GET','HEAD','OPTIONS'):
        return PlainTextResponse('Talent Bridge is in preview mode. Registrations, enquiries and uploads are temporarily disabled until permanent secure storage is configured.',status_code=503,headers={'Cache-Control':'no-store'})
    request.state.user=None;request.state.csrf=None
    sid=request.cookies.get('tb_session','')
    if sid:
        with db() as c:
            row=c.execute('select users.*,sessions.csrf from sessions join users on users.id=sessions.user_id where sessions.id_hash=? and sessions.expires_at>?',(token_hash(sid),int(time.time()))).fetchone()
            if row:request.state.user=dict(row);request.state.csrf=row['csrf']
    response=await call_next(request)
    response.headers['Cache-Control']='no-store' if request.url.path.startswith(('/admin','/dashboard','/candidate','/documents','/hire')) else 'public, max-age=0'
    response.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
    if os.environ.get('COOKIE_SECURE')=='1':response.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'
    response.headers['X-Content-Type-Options']='nosniff';response.headers['Referrer-Policy']='strict-origin-when-cross-origin';response.headers['X-Frame-Options']='DENY'
    response.headers['Content-Security-Policy']="default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; script-src 'self'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    return response

@app.get('/',response_class=HTMLResponse)
def home(request:Request):
    with db() as c:jobs=c.execute('select * from jobs where published=1 order by id desc limit 3').fetchall()
    return render(request,'home.html',jobs=jobs)

@app.get('/about')
def about(request:Request):return render(request,'about.html',title='About Talent Bridge | Our Mission and Approach')
@app.get('/services')
def services(request:Request):return render(request,'services.html',title='Recruitment Services | Talent Bridge',items=[('IT Recruitment','Build technology teams across development, data, cloud, testing and IT operations.',['Software','Data & AI','IT Support']),('Non-IT Recruitment','Find people for essential business functions and sector-specific operational roles.',['Operations','Business Functions','Specialists']),('BFSI Recruitment','Connect with talent for banking, financial services, insurance and related functions.',['Banking','Finance','Insurance']),('Sales & Business Development','Grow teams responsible for relationships, market expansion and revenue development.',['Sales','Business Development','Account Management']),('HR & Administration','Support recruitment for people operations, administrative coordination and HR teams.',['Human Resources','Administration','People Operations']),('Customer Support & Operations','Hire customer-facing professionals and operations support teams.',['Customer Service','Support','Operations'])])
@app.get('/privacy')
def privacy(request:Request):return render(request,'info.html',title='Privacy Information',intro='This draft privacy summary must be reviewed and replaced with your approved policy before going live.',sections=[('Information collected','We collect account details, recruitment information, uploaded resumes and job descriptions, and contact messages.'),('Use of information','Information is used to manage hiring enquiries, candidate profiles and job applications. Candidate profiles may be shared with relevant employers only with recorded consent and appropriate access.'),('Contact and retention','Publish a verified business privacy contact, retention period, withdrawal and deletion process before production release.')])

@app.get('/register')
def register_get(request:Request):return render(request,'auth.html',mode='register',error=None)
@app.post('/register')
async def register_post(request:Request):
    if not throttle(request,'register',8):return render(request,'auth.html',mode='register',error='Too many attempts. Please try later.',status=429)
    f=await request.form();role=normal(f.get('role'),15);name=normal(f.get('name'),120);email=normal(f.get('email'),254).lower();phone=normal(f.get('phone'),30);company=normal(f.get('company'),160);password=str(f.get('password',''))
    if role not in ('candidate','employer') or len(name)<2 or not mail_ok(email) or len(password)<10 or len(password)>128:return render(request,'auth.html',mode='register',error='Enter a valid name, email and a password of at least 10 characters.',status=400)
    if not normal(f.get('website'),1)=='':return render(request,'auth.html',mode='register',error='Invalid submission.',status=400)
    with db() as c:
        try:
            c.execute('insert into users(name,email,phone,role,pw_hash,company,created_at) values(?,?,?,?,?,?,?)',(name,email,phone,role,pw_hash(password),company,utc()))
        except Exception:return render(request,'auth.html',mode='register',error='This email is already registered.',status=400)
    return go('/login?registered=1')

@app.get('/login')
def login_get(request:Request):return render(request,'auth.html',mode='login',error=None)
@app.post('/login')
async def login_post(request:Request):
    if not throttle(request,'login',20,900):return render(request,'auth.html',mode='login',error='Too many attempts. Try again later.',status=429)
    f=await request.form();email=normal(f.get('email'),254).lower();pwd=str(f.get('password',''))
    with db() as c:
        row=c.execute('select * from users where email=?',(email,)).fetchone()
        if not row or not verify_pw(pwd,row['pw_hash']):return render(request,'auth.html',mode='login',error='Invalid email or password.',status=401)
        sid=secrets.token_urlsafe(48);csrf=secrets.token_urlsafe(32)
        c.execute('insert into sessions(id_hash,user_id,csrf,expires_at) values(?,?,?,?)',(token_hash(sid),row['id'],csrf,int(time.time())+604800))
        role=row['role']
    response=go('/dashboard' if role!='admin' else '/admin');response.set_cookie('tb_session',sid,httponly=True,secure=os.environ.get('COOKIE_SECURE','0')=='1',samesite='lax',max_age=604800,path='/');return response

@app.post('/logout')
async def logout(request:Request):
    f=await request.form()
    if not check_csrf(request,f):return PlainTextResponse('Invalid CSRF token',status_code=403)
    with db() as c:c.execute('delete from sessions where id_hash=?',(token_hash(request.cookies.get('tb_session','')),))
    response=go('/');response.delete_cookie('tb_session');return response

async def save_upload(f,owner,kind):
    if not isinstance(f,UploadFile) or not f.filename:return None
    name=Path(f.filename).name[:160];ext=Path(name).suffix.lower()
    if ext not in ('.pdf','.docx'):raise ValueError('Only PDF and DOCX files are allowed.')
    data=await f.read(MAX_UPLOAD+1)
    if not data or len(data)>MAX_UPLOAD:raise ValueError('Upload must be under 5 MB.')
    if ext=='.pdf' and not data.startswith(b'%PDF-'):raise ValueError('Invalid PDF file.')
    if ext=='.docx':
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names=set(archive.namelist())
                if 'word/document.xml' not in names or '[Content_Types].xml' not in names:
                    raise ValueError('Invalid DOCX document.')
                if len(names)>1500 or sum(x.file_size for x in archive.infolist())>40*1024*1024:
                    raise ValueError('DOCX contents exceed safety limits.')
        except (zipfile.BadZipFile,ValueError) as e:
            raise ValueError('Invalid or unsafe DOCX document.') from e
    storage=secrets.token_hex(24)+ext
    destination=UPLOAD_DIR/storage
    with destination.open('xb') as output:output.write(data)
    try:destination.chmod(0o600)
    except OSError:pass
    with db() as c:
        cur=c.execute('insert into documents(owner_user_id,kind,storage_name,original_name,mime,created_at) values(?,?,?,?,?,?)',(owner,kind,storage,name,'application/pdf' if ext=='.pdf' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',utc()))
        return cur.lastrowid

@app.get('/dashboard')
def dashboard(request:Request):
    deny=require(request)
    if deny:return deny
    u=session_user(request)
    if u['role']=='admin':return go('/admin')
    with db() as c:
        if u['role']=='employer':items=c.execute('select * from employer_enquiries where user_id=? order by id desc',(u['id'],)).fetchall()
        else:items=c.execute('select applications.*,jobs.title,jobs.company from applications join jobs on jobs.id=applications.job_id where candidate_id=? order by applications.id desc',(u['id'],)).fetchall()
        profile=c.execute('select * from candidates where user_id=?',(u['id'],)).fetchone() if u['role']=='candidate' else None
    return render(request,'dashboard.html',items=items,profile=profile)

@app.get('/hire')
def hire_get(request:Request):
    deny=require(request,'employer')
    if deny:return deny
    return render(request,'hire.html',error=None)
@app.post('/hire')
async def hire_post(request:Request):
    deny=require(request,'employer')
    if deny:return deny
    f=await request.form();u=session_user(request)
    if not check_csrf(request,f):return PlainTextResponse('Invalid CSRF token',status_code=403)
    if not throttle(request,'hire',20):return PlainTextResponse('Too many submissions',status_code=429)
    company=normal(f.get('company_name'),160);person=normal(f.get('contact_person'),120);email=normal(f.get('email'),254);phone=normal(f.get('phone'),30);role=normal(f.get('job_role'),140);location=normal(f.get('location'),140);desc=normal(f.get('description'),12000)
    try:openings=int(str(f.get('openings','0')))
    except ValueError:openings=0
    if not all((company,person,mail_ok(email),phone,role,location,desc)) or not 1<=openings<=10000:return render(request,'hire.html',error='Please complete all required fields correctly.',status=400)
    try:doc_id=await save_upload(f.get('jd'),u['id'],'jd')
    except ValueError as e:return render(request,'hire.html',error=str(e),status=400)
    with db() as c:
        c.execute('insert into employer_enquiries(user_id,company_name,contact_person,email,phone,job_role,openings,location,description,document_id,created_at) values(?,?,?,?,?,?,?,?,?,?,?)',(u['id'],company,person,email,phone,role,openings,location,desc,doc_id,utc()))
    notification('New Talent Bridge hiring enquiry',f'{company} requested {openings} openings for {role} in {location}. Sign in to review.')
    return go('/dashboard?submitted=1')

@app.get('/candidate/profile')
def candidate_get(request:Request):
    deny=require(request,'candidate')
    if deny:return deny
    with db() as c:profile=c.execute('select * from candidates where user_id=?',(session_user(request)['id'],)).fetchone()
    return render(request,'candidate.html',profile=profile,error=None)
@app.post('/candidate/profile')
async def candidate_post(request:Request):
    deny=require(request,'candidate')
    if deny:return deny
    f=await request.form();u=session_user(request)
    if not check_csrf(request,f):return PlainTextResponse('Invalid CSRF token',status_code=403)
    location=normal(f.get('location'),140);experience=normal(f.get('experience'),90);skills=normal(f.get('skills'),1000);preferred=normal(f.get('preferred_role'),140);consent=int(f.get('consent','0')=='yes')
    with db() as c:old=c.execute('select * from candidates where user_id=?',(u['id'],)).fetchone()
    if not all((location,experience,skills,preferred)) or not consent:return render(request,'candidate.html',profile=old,error='All fields and profile-sharing consent are required.',status=400)
    try:resume_id=await save_upload(f.get('resume'),u['id'],'resume')
    except ValueError as e:return render(request,'candidate.html',profile=old,error=str(e),status=400)
    if not resume_id and not (old and old['resume_id']):return render(request,'candidate.html',profile=old,error='Please upload a resume (PDF or DOCX).',status=400)
    with db() as c:
        if old:c.execute('update candidates set location=?,experience=?,skills=?,preferred_role=?,consent=?,consent_at=?,resume_id=? where user_id=?',(location,experience,skills,preferred,1,utc(),resume_id or old['resume_id'],u['id']))
        else:c.execute('insert into candidates(user_id,location,experience,skills,preferred_role,consent,consent_at,resume_id,created_at) values(?,?,?,?,?,?,?,?,?)',(u['id'],location,experience,skills,preferred,1,utc(),resume_id,utc()))
    if not old:notification('New Talent Bridge candidate registration',f'Candidate {u["name"]} registered with preferred role {preferred}. Sign in to review.')
    return go('/dashboard?profile=1')

@app.get('/jobs')
def jobs_get(request:Request,q:str=''):
    with db() as c:
        if q:jobs=c.execute('select * from jobs where published=1 and (title like ? or location like ? or category like ?) order by id desc',tuple(['%'+q[:80]+'%']*3)).fetchall()
        else:jobs=c.execute('select * from jobs where published=1 order by id desc').fetchall()
    return render(request,'jobs.html',jobs=jobs,q=q)
@app.post('/jobs/{job_id}/apply')
async def apply(request:Request,job_id:int):
    deny=require(request,'candidate')
    if deny:return deny
    f=await request.form()
    if not check_csrf(request,f):return PlainTextResponse('Invalid CSRF token',status_code=403)
    u=session_user(request)
    with db() as c:
        candidate=c.execute('select * from candidates where user_id=?',(u['id'],)).fetchone()
        job=c.execute('select * from jobs where id=? and published=1',(job_id,)).fetchone()
        if not job:return PlainTextResponse('Job not found',status_code=404)
        if not candidate:return go('/candidate/profile')
        c.execute('insert or ignore into applications(job_id,candidate_id,created_at) values(?,?,?)',(job_id,u['id'],utc()))
    return go('/dashboard?applied=1')

@app.get('/contact')
def contact_get(request:Request):return render(request,'contact.html',error=None)
@app.post('/contact')
async def contact_post(request:Request):
    if not throttle(request,'contact',6):return render(request,'contact.html',error='Too many messages. Please try again later.',status=429)
    f=await request.form();name=normal(f.get('name'),120);email=normal(f.get('email'),254);phone=normal(f.get('phone'),30);message=normal(f.get('message'),3000)
    if f.get('website'):return go('/contact?sent=1') # honeypot
    if not name or not mail_ok(email) or len(message)<10:return render(request,'contact.html',error='Please enter your name, valid email and a message of 10+ characters.',status=400)
    with db() as c:c.execute('insert into contacts(name,email,phone,message,created_at) values(?,?,?,?,?)',(name,email,phone,message,utc()))
    notification('New Talent Bridge contact enquiry',f'New message from {name} ({email}). Review in admin.')
    return go('/contact?sent=1')

@app.get('/documents/{document_id}')
def download(request:Request,document_id:int):
    deny=require(request)
    if deny:return deny
    u=session_user(request)
    with db() as c:doc=c.execute('select * from documents where id=?',(document_id,)).fetchone()
    if not doc:return PlainTextResponse('Not found',status_code=404)
    if u['role']!='admin' and doc['owner_user_id']!=u['id']:return PlainTextResponse('Access denied',status_code=403)
    path=UPLOAD_DIR/doc['storage_name']
    if not path.is_file():return PlainTextResponse('File unavailable',status_code=404)
    return FileResponse(path,media_type=doc['mime'],filename=doc['original_name'],headers={'Cache-Control':'private, no-store'})

@app.get('/admin')
def admin_home(request:Request,tab:str='overview',q:str='',status_filter:str='',experience_filter:str=''):
    deny=require(request,'admin')
    if deny:return deny
    if tab not in ('overview','candidates','enquiries','jobs','applications','contacts','activity'):tab='overview'
    with db() as c:
        counts={name:c.execute(f'select count(*) from {name}').fetchone()[0] for name in ('candidates','employer_enquiries','jobs','applications','contacts')}
        if tab=='candidates':
            sql='select candidates.*,users.name,users.email,users.phone from candidates join users on users.id=candidates.user_id where (users.name like ? or candidates.skills like ? or candidates.location like ? or candidates.preferred_role like ?)'
            args=['%'+q[:100]+'%']*4
            if status_filter in STATUS['candidate']:
                sql+=' and candidates.status=?';args.append(status_filter)
            if experience_filter:
                sql+=' and candidates.experience like ?';args.append('%'+experience_filter[:60]+'%')
            records=c.execute(sql+' order by candidates.id desc limit 500',args).fetchall()
        elif tab=='enquiries':records=c.execute('select * from employer_enquiries order by id desc').fetchall()
        elif tab=='jobs':records=c.execute('select * from jobs order by id desc').fetchall()
        elif tab=='applications':records=c.execute('select applications.*,jobs.title,users.name,users.email from applications join jobs on jobs.id=applications.job_id join users on users.id=applications.candidate_id order by applications.id desc').fetchall()
        elif tab=='contacts':records=c.execute('select * from contacts order by id desc').fetchall()
        elif tab=='activity':records=c.execute('select activity_log.*,users.email from activity_log join users on users.id=activity_log.admin_user_id order by activity_log.id desc limit 100').fetchall()
        else:records=c.execute('select * from employer_enquiries order by id desc limit 5').fetchall()
    return render(request,'admin.html',tab=tab,records=records,counts=counts,statuses=STATUS,q=q,status_filter=status_filter,experience_filter=experience_filter)

@app.post('/admin/status')
async def admin_status(request:Request):
    deny=require(request,'admin')
    if deny:return deny
    f=await request.form()
    if not check_csrf(request,f):return PlainTextResponse('Invalid CSRF token',status_code=403)
    kind=normal(f.get('kind'),30);status=normal(f.get('status'),50);tab=normal(f.get('tab'),30)
    tables={'candidate':'candidates','enquiry':'employer_enquiries','application':'applications','contact':'contacts'}
    if kind not in tables or status not in STATUS[kind]:return PlainTextResponse('Invalid status',status_code=400)
    try:item_id=int(f.get('id',''))
    except ValueError:return PlainTextResponse('Invalid id',status_code=400)
    with db() as c:
        c.execute(f'update {tables[kind]} set status=? where id=?',(status,item_id))
        audit(c,session_user(request),kind,item_id,'status -> '+status)
    return go('/admin?tab='+quote(tab))

@app.post('/admin/jobs')
async def admin_jobs(request:Request):
    deny=require(request,'admin')
    if deny:return deny
    f=await request.form()
    if not check_csrf(request,f):return PlainTextResponse('Invalid CSRF token',status_code=403)
    title=normal(f.get('title'),160);company=normal(f.get('company'),160);location=normal(f.get('location'),120);category=normal(f.get('category'),100);description=normal(f.get('description'),6000);employment=normal(f.get('employment_type'),60);published=int(f.get('published')=='1')
    if not all((title,company,location,category,description)):return PlainTextResponse('All job fields are required.',status_code=400)
    with db() as c:
        cursor=c.execute('insert into jobs(title,company,location,category,description,employment_type,published,created_by,created_at) values(?,?,?,?,?,?,?,?,?)',(title,company,location,category,description,employment or 'Full-time',published,session_user(request)['id'],utc()))
        audit(c,session_user(request),'job',cursor.lastrowid,'created')
    return go('/admin?tab=jobs')

@app.post('/admin/jobs/{job_id}/toggle')
async def toggle_job(request:Request,job_id:int):
    deny=require(request,'admin')
    if deny:return deny
    f=await request.form()
    if not check_csrf(request,f):return PlainTextResponse('Invalid CSRF token',status_code=403)
    with db() as c:
        c.execute('update jobs set published=1-published where id=?',(job_id,))
        audit(c,session_user(request),'job',job_id,'toggle published')
    return go('/admin?tab=jobs')

@app.get('/robots.txt')
def robots():return PlainTextResponse('User-agent: *\nDisallow: /admin\nDisallow: /dashboard\nDisallow: /candidate/\nDisallow: /documents/\nDisallow: /login\nDisallow: /register\n')


@app.get('/healthz')
def healthz():
    try:
        with db() as c:c.execute('select 1').fetchone()
        return JSONResponse({'status':'ok'})
    except Exception:
        return JSONResponse({'status':'unavailable'},status_code=503)

@app.get('/admin/export/{dataset}')
def admin_export(request:Request,dataset:str):
    denied=require(request,'admin')
    if denied:return denied
    definitions={
      'candidates':('select users.name,users.email,users.phone,candidates.location,candidates.experience,candidates.skills,candidates.preferred_role,candidates.status,candidates.consent_at,candidates.created_at from candidates join users on users.id=candidates.user_id order by candidates.id desc',('name','email','phone','location','experience','skills','preferred_role','status','consent_at','created_at')),
      'enquiries':('select company_name,contact_person,email,phone,job_role,openings,location,description,status,created_at from employer_enquiries order by id desc',('company_name','contact_person','email','phone','job_role','openings','location','description','status','created_at')),
      'applications':('select users.name,users.email,jobs.title,applications.status,applications.created_at from applications join users on users.id=applications.candidate_id join jobs on jobs.id=applications.job_id order by applications.id desc',('candidate_name','candidate_email','job_title','status','created_at')),
      'contacts':('select name,email,phone,message,status,created_at from contacts order by id desc',('name','email','phone','message','status','created_at')),
      'jobs':('select title,company,location,category,employment_type,description,published,created_at from jobs order by id desc',('title','company','location','category','employment_type','description','published','created_at')),
    }
    if dataset not in definitions:return PlainTextResponse('Unknown export',status_code=404)
    query,columns=definitions[dataset]
    with db() as c:rows=c.execute(query).fetchall()
    output=io.StringIO();output.write('\ufeff');writer=csv.writer(output);writer.writerow(columns)
    for record in rows:
        # neutralize spreadsheet formulas in untrusted, recruiter-entered text
        writer.writerow([("'"+str(value) if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')) else value) for value in record])
    return StreamingResponse(iter([output.getvalue().encode('utf-8')]),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="talentbridge-{dataset}.csv"','Cache-Control':'private, no-store'})

@app.post('/admin/jobs/{job_id}/edit')
async def admin_job_edit(request:Request,job_id:int):
    denied=require(request,'admin')
    if denied:return denied
    f=await request.form()
    if not check_csrf(request,f):return PlainTextResponse('Invalid CSRF token',status_code=403)
    values=[normal(f.get(k),maxlen) for k,maxlen in [('title',160),('company',160),('location',120),('category',100),('employment_type',60),('description',6000)]]
    if not all(values):return PlainTextResponse('All job fields are required',status_code=400)
    with db() as c:
        if not c.execute('select 1 from jobs where id=?',(job_id,)).fetchone():return PlainTextResponse('Job not found',status_code=404)
        c.execute('update jobs set title=?,company=?,location=?,category=?,employment_type=?,description=? where id=?',(*values,job_id))
        audit(c,session_user(request),'job',job_id,'updated')
    return go('/admin?tab=jobs')
