#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,math,re,shutil,struct,sys,urllib.request,zipfile
from pathlib import Path
LDRAW_OFFICIAL_URL="https://library.ldraw.org/library/updates/complete.zip"
LDRAW_UNOFFICIAL_URL="https://library.ldraw.org/library/unofficial/ldrawunf.zip"
SCALE_MM=0.4
ALIASES={"43093":["43093"],"4599b":["4599b","4599"],"73109":["73109"]}
SUPPLEMENTS=[]
def safe_name(s):
    s=re.sub(r"[^A-Za-z0-9._-]+","_",s.strip()); return s.strip("_") or "unknown"
def download(url,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists() and target.stat().st_size>1024:return
    print("[download]",url)
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req,timeout=180) as r,open(target,"wb") as f:shutil.copyfileobj(r,f)
def extract_zip(src,dest):
    marker=dest/".ok"
    if marker.exists():return
    dest.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(src) as z:z.extractall(dest)
    marker.write_text("ok")
def find_roots(a,b):
    roots=[]
    for top in (b,a):
        for c in (top/"ldraw",top/"LDraw",top):
            if (c/"parts").exists() or (c/"p").exists():
                roots.append(c);break
    if not roots:raise RuntimeError("LDraw roots not found")
    return roots
def identity():return (1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.)
def compose(p,c):
    pa,pb,pc,pd,pe,pf,pg,ph,pi,px,py,pz=p
    ca,cb,cc,cd,ce,cf,cg,ch,ci,cx,cy,cz=c
    return (pa*ca+pb*cd+pc*cg,pa*cb+pb*ce+pc*ch,pa*cc+pb*cf+pc*ci,pd*ca+pe*cd+pf*cg,pd*cb+pe*ce+pf*ch,pd*cc+pe*cf+pf*ci,pg*ca+ph*cd+pi*cg,pg*cb+ph*ce+pi*ch,pg*cc+ph*cf+pi*ci,pa*cx+pb*cy+pc*cz+px,pd*cx+pe*cy+pf*cz+py,pg*cx+ph*cy+pi*cz+pz)
def transform(t,p):
    a,b,c,d,e,f,g,h,i,x,y,z=t;px,py,pz=p
    return (a*px+b*py+c*pz+x,d*px+e*py+f*pz+y,g*px+h*py+i*pz+z)
def det(t):
    a,b,c,d,e,f,g,h,i,*_=t
    return a*(e*i-f*h)-b*(d*i-f*g)+c*(d*h-e*g)
class Resolver:
    def __init__(self,roots):self.roots=roots;self.cache={};self.lower={}
    def candidates(self,root,ref):
        ref=ref.replace("\\","/").lstrip("./");low=ref.lower()
        if low.startswith(("parts/","p/")):yield root/ref
        elif low.startswith("s/"):yield root/"parts"/ref
        elif low.startswith(("48/","8/")):yield root/"p"/ref
        else:
            yield root/"parts"/ref;yield root/"p"/ref;yield root/"parts"/"s"/ref;yield root/"p"/"48"/ref;yield root/"p"/"8"/ref
    def resolve(self,ref):
        key=ref.replace("\\","/").lstrip("./").lower()
        if key in self.cache:return self.cache[key]
        for root in self.roots:
            for p in self.candidates(root,ref):
                if p.exists():self.cache[key]=p;return p
                par=p.parent
                if par.exists():
                    lm=self.lower.get(par)
                    if lm is None:
                        try:lm={q.name.lower():q for q in par.iterdir() if q.is_file()}
                        except OSError:lm={}
                        self.lower[par]=lm
                    if p.name.lower() in lm:self.cache[key]=lm[p.name.lower()];return self.cache[key]
        self.cache[key]=None;return None
class Mesh:
    def __init__(self,r):self.r=r;self.fc={};self.missing=set();self.guard=set()
    def lines(self,p):
        if p not in self.fc:self.fc[p]=p.read_text(encoding="utf-8",errors="ignore").splitlines()
        return self.fc[p]
    def expand(self,ref):
        p=self.r.resolve(ref if ref.lower().endswith(".dat") else ref+".dat")
        if not p:self.missing.add(ref);return []
        tris=[];self.walk(p,identity(),tris,0);return tris
    def walk(self,path,t,tris,depth):
        if depth>80:return
        g=(path,tuple(round(v,10) for v in t))
        if g in self.guard:return
        self.guard.add(g)
        try:
            for raw in self.lines(path):
                f=raw.strip().split()
                if not f:continue
                typ=f[0]
                if typ=="1" and len(f)>=15:
                    vals=[float(x) for x in f[2:14]]
                    x,y,z,a,b,c,d,e,ff,gg,h,i=vals
                    child=(a,b,c,d,e,ff,gg,h,i,x,y,z)
                    rp=self.r.resolve(" ".join(f[14:]))
                    if rp:self.walk(rp,compose(t,child),tris,depth+1)
                    else:self.missing.add(" ".join(f[14:]))
                elif typ=="3" and len(f)>=11:
                    vals=[float(x) for x in f[2:11]];p=[transform(t,tuple(vals[k:k+3])) for k in (0,3,6)]
                    if det(t)<0:p[1],p[2]=p[2],p[1]
                    tris.append(tuple(p))
                elif typ=="4" and len(f)>=14:
                    vals=[float(x) for x in f[2:14]];p=[transform(t,tuple(vals[k:k+3])) for k in (0,3,6,9)]
                    if det(t)<0:p=[p[0],p[3],p[2],p[1]]
                    tris.extend(((p[0],p[1],p[2]),(p[0],p[2],p[3])))
        finally:self.guard.discard(g)
def normal(a,b,c):
    ux,uy,uz=b[0]-a[0],b[1]-a[1],b[2]-a[2];vx,vy,vz=c[0]-a[0],c[1]-a[1],c[2]-a[2]
    nx,ny,nz=uy*vz-uz*vy,uz*vx-ux*vz,ux*vy-uy*vx;l=math.sqrt(nx*nx+ny*ny+nz*nz)
    return (0.,0.,0.) if l<1e-12 else (nx/l,ny/l,nz/l)
def write_stl(path,tris):
    out=[];minz=float("inf")
    for tri in tris:
        q=[]
        for x,y,z in tri:
            v=(x*SCALE_MM,z*SCALE_MM,-y*SCALE_MM);minz=min(minz,v[2]);q.append(v)
        out.append(q)
    if minz==float("inf"):raise ValueError("No triangles")
    dz=-minz;path.parent.mkdir(parents=True,exist_ok=True)
    with open(path,"wb") as f:
        f.write(b"LEGO 30708 from LDraw".ljust(80,b"\0"));f.write(struct.pack("<I",len(out)))
        for tri in out:
            tri=[(x,y,z+dz) for x,y,z in tri];n=normal(*tri)
            f.write(struct.pack("<12fH",n[0],n[1],n[2],tri[0][0],tri[0][1],tri[0][2],tri[1][0],tri[1][1],tri[1][2],tri[2][0],tri[2][1],tri[2][2],0))
    return len(out)
def load(path):
    with open(path,newline="",encoding="utf-8-sig") as f:data=list(csv.DictReader(f))
    rows=[((r.get("part")or"").strip(),int(r.get("qty")or 0),(r.get("colour")or"").strip(),(r.get("description")or"").strip(),"inventory") for r in data if (r.get("part")or"").strip()]
    rows += [(p,q,c,d,"supplement") for p,q,c,d in SUPPLEMENTS]
    return rows
def main():
    here=Path(__file__).resolve().parent;work=here/"_ldraw_cache";output=here/"STL_30708"
    d=work/"downloads";download(LDRAW_OFFICIAL_URL,d/"complete.zip");download(LDRAW_UNOFFICIAL_URL,d/"ldrawunf.zip")
    extract_zip(d/"complete.zip",work/"official");extract_zip(d/"ldrawunf.zip",work/"unofficial")
    r=Resolver(find_roots(work/"official",work/"unofficial"));m=Mesh(r);items=load(here/"inventory_30708.csv");report=[]
    for idx,(part,qty,color,desc,src) in enumerate(items,1):
        used=None;tris=[];missing=set()
        for cand in [part]+ALIASES.get(part,[]):
            m.missing.clear();tris=m.expand(cand);missing=set(m.missing)
            if tris and not missing:used=cand;break
        if used:
            n=write_stl(output/safe_name(color)/(safe_name(part)+"_x"+str(qty)+".stl"),tris);status="OK"
            print(f"[OK {idx}/{len(items)}] {part}->{used} x{qty}")
        else:
            n=len(tris);status="MISSING_OR_INCOMPLETE";print(f"[MISS {idx}/{len(items)}] {part} x{qty}")
        report.append([part,qty,color,desc,src,status,used or "",n,";".join(sorted(missing))])
    output.mkdir(parents=True,exist_ok=True)
    with open(output/"_conversion_report.csv","w",newline="",encoding="utf-8") as f:
        w=csv.writer(f);w.writerow(["part","qty","colour","description","source","status","ldraw_used","triangles","missing_refs"]);w.writerows(report)
    miss=sum(1 for x in report if x[5]!="OK");print("Missing unique items:",miss)
if __name__=="__main__":main()

