import os,sys,tempfile,io
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
TMP=tempfile.TemporaryDirectory()
os.environ['TALENTBRIDGE_DB']=str(Path(TMP.name)/'test.sqlite3')
os.environ['TALENTBRIDGE_UPLOADS']=str(Path(TMP.name)/'uploads')
from fastapi.testclient import TestClient
from app.main import app
from app.db import db,pw_hash,utc


def sign_up(client,name,email,role):
    r=client.post('/register',data={'name':name,'email':email,'phone':'9999999999','role':role,'company':'Sample Corp','password':'secure-test-password'},follow_redirects=False)
    assert r.status_code==303,r.text
    r=client.post('/login',data={'email':email,'password':'secure-test-password'},follow_redirects=False)
    assert r.status_code==303,r.text
    assert 'tb_session' in client.cookies

def csrf(client):
    from app.db import db
    from app.main import token_hash
    with db() as c:return c.execute('select csrf from sessions where id_hash=?',(token_hash(client.cookies['tb_session']),)).fetchone()['csrf']

def test_complete_platform():
 with TestClient(app) as public,TestClient(app) as emp,TestClient(app) as cand,TestClient(app) as admin:
    assert public.get('/').status_code==200
    assert public.get('/admin',follow_redirects=False).status_code==303
    sign_up(emp,'Employer Contact','employer@example.com','employer')
    assert emp.get('/hire').status_code==200
    upload=b'%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n'
    r=emp.post('/hire',data={'csrf':csrf(emp),'company_name':'Sample Corp','contact_person':'Employer Contact','email':'employer@example.com','phone':'9999999999','job_role':'Python Engineer','openings':'2','location':'Delhi','description':'Build recruitment software.'},files={'jd':('role.pdf',upload,'application/pdf')},follow_redirects=False)
    assert r.status_code==303,r.text
    assert 'Python Engineer' in emp.get('/dashboard').text
    sign_up(cand,'Candidate One','candidate@example.com','candidate')
    r=cand.post('/candidate/profile',data={'csrf':csrf(cand),'location':'Bhopal','experience':'1 year','skills':'Python, SQL','preferred_role':'Python Engineer','consent':'yes'},files={'resume':('resume.pdf',upload,'application/pdf')},follow_redirects=False)
    assert r.status_code==303,r.text
    with db() as conn:
       emp_enq=conn.execute('select * from employer_enquiries').fetchone()
       profile=conn.execute('select * from candidates').fetchone()
       assert emp_enq['document_id'] and profile['resume_id']
       assert conn.execute('select count(*) from sessions').fetchone()[0]==2
    assert cand.get(f'/documents/{emp_enq["document_id"]}').status_code==403
    assert cand.get(f'/documents/{profile["resume_id"]}').status_code==200
    assert public.get(f'/documents/{profile["resume_id"]}',follow_redirects=False).status_code==303
    with db() as conn:
       conn.execute('insert into users(name,email,role,pw_hash,created_at) values(?,?,?,?,?)',('Administrator','admin@example.com','admin',pw_hash('secure-admin-password'),utc()))
    r=admin.post('/login',data={'email':'admin@example.com','password':'secure-admin-password'},follow_redirects=False)
    assert r.status_code==303
    r=admin.get('/admin?tab=candidates');assert r.status_code==200 and 'Candidate One' in r.text
    r=admin.get('/admin?tab=enquiries');assert r.status_code==200 and 'Python Engineer' in r.text
    assert admin.get(f'/documents/{profile["resume_id"]}').status_code==200
    r=admin.post('/admin/jobs',data={'csrf':csrf(admin),'title':'Python Engineer','company':'Sample Corp','location':'Delhi','category':'IT Recruitment','description':'Build robust apps.','employment_type':'Full-time','published':'1'},follow_redirects=False)
    assert r.status_code==303
    assert 'Python Engineer' in public.get('/jobs').text
    with db() as conn:job_id=conn.execute('select id from jobs').fetchone()['id']
    r=cand.post(f'/jobs/{job_id}/apply',data={'csrf':csrf(cand)},follow_redirects=False);assert r.status_code==303
    assert 'Python Engineer' in cand.get('/dashboard').text
    assert 'Candidate One' in admin.get('/admin?tab=applications').text
    r=admin.post('/admin/status',data={'csrf':csrf(admin),'kind':'candidate','id':str(profile['id']),'status':'shortlisted','tab':'candidates'},follow_redirects=False)
    assert r.status_code==303
    with db() as conn:assert conn.execute('select status from candidates').fetchone()['status']=='shortlisted'
    assert admin.post('/admin/status',data={'csrf':'invalid','kind':'candidate','id':str(profile['id']),'status':'placed','tab':'candidates'}).status_code==403
    r=public.post('/contact',data={'name':'Visitor','email':'visitor@example.com','message':'Please call me about recruitment.'},follow_redirects=False)
    assert r.status_code==303
    assert 'Visitor' in admin.get('/admin?tab=contacts').text
    assert emp.get('/admin',follow_redirects=False).status_code==403
    assert cand.get('/hire',follow_redirects=False).status_code==403
    out=cand.post('/logout',data={'csrf':csrf(cand)},follow_redirects=False)
    assert out.status_code==303
    assert cand.get('/dashboard',follow_redirects=False).status_code==303


def test_bad_upload_rejected():
 with TestClient(app) as emp:
    sign_up(emp,'Another Employer','different@example.com','employer')
    r=emp.post('/hire',data={'csrf':csrf(emp),'company_name':'Another Co','contact_person':'Person','email':'different@example.com','phone':'1000000000','job_role':'Designer','openings':'1','location':'Remote','description':'Designer role'},files={'jd':('malware.pdf',b'not a PDF','application/pdf')},follow_redirects=False)
    assert r.status_code==400


def test_admin_exports_job_edit_and_health():
 with TestClient(app) as client:
    assert client.get('/healthz').json()['status']=='ok'
    assert client.get('/admin/export/candidates',follow_redirects=False).status_code==303
    # Use an independent admin user.
    with db() as conn:
        conn.execute('insert into users(name,email,role,pw_hash,created_at) values(?,?,?,?,?)',('CSV Admin','exports-admin@example.com','admin',pw_hash('export-admin-password'),utc()))
    response=client.post('/login',data={'email':'exports-admin@example.com','password':'export-admin-password'},follow_redirects=False)
    assert response.status_code==303
    response=client.post('/admin/jobs',data={'csrf':csrf(client),'title':'Data Analyst','company':'Test Company','location':'Bhopal','category':'Data','description':'Analyze data for reporting.','employment_type':'Full-time','published':'1'},follow_redirects=False)
    assert response.status_code==303
    with db() as conn:
       job_id=conn.execute('select id from jobs where title=?',('Data Analyst',)).fetchone()['id']
    edited=client.post(f'/admin/jobs/{job_id}/edit',data={'csrf':csrf(client),'title':'Senior Data Analyst','company':'Test Company','location':'Delhi','category':'Data','description':'Analyze business data responsibly.','employment_type':'Contract'},follow_redirects=False)
    assert edited.status_code==303
    assert 'Senior Data Analyst' in client.get('/admin?tab=jobs').text
    csv_result=client.get('/admin/export/jobs')
    assert csv_result.status_code==200
    assert 'text/csv' in csv_result.headers['content-type']
    assert 'Senior Data Analyst' in csv_result.text
    assert client.get('/admin/export/unknown').status_code==404
    assert client.get('/admin?tab=candidates&status_filter=screening&experience_filter=2').status_code==200
    invalid=client.post(f'/admin/jobs/{job_id}/edit',data={'csrf':'bad','title':'invalid'},follow_redirects=False)
    assert invalid.status_code==403
