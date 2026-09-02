#!/usr/bin/env python3
from pathlib import Path
import struct,re,csv,zipfile

ROOT=Path(__file__).resolve().parent
SRC=ROOT/"STL_30708"
OUT=ROOT/"REMOTE_PLATES_30708"
BED=260.0; MARGIN=7.0; SPACING=5.0; MAXN=40

def read_stl(path):
    data=path.read_bytes(); n=struct.unpack_from("<I",data,80)[0]; off=84; tris=[]
    for _ in range(n):
        v=struct.unpack_from("<12fH",data,off)
        tris.append([[v[3],v[4],v[5]],[v[6],v[7],v[8]],[v[9],v[10],v[11]]]); off+=50
    return tris
def bbox(t):
    pts=[p for tr in t for p in tr]
    xs=[p[0] for p in pts]; ys=[p[1] for p in pts]; zs=[p[2] for p in pts]
    return min(xs),min(ys),min(zs),max(xs),max(ys),max(zs)
def norm(t):
    a,b,c,d,e,f=bbox(t)
    return [[[x-a,y-b,z-c] for x,y,z in tr] for tr in t]
def rot(t): return norm([[[-y,x,z] for x,y,z in tr] for tr in t])
def trans(t,dx,dy): return [[[x+dx,y+dy,z] for x,y,z in tr] for tr in t]
def normal(a,b,c):
    ux,uy,uz=b[0]-a[0],b[1]-a[1],b[2]-a[2]; vx,vy,vz=c[0]-a[0],c[1]-a[1],c[2]-a[2]
    nx,ny,nz=uy*vz-uz*vy,uz*vx-ux*vz,ux*vy-uy*vx; L=(nx*nx+ny*ny+nz*nz)**.5
    return (0,0,0) if L<1e-12 else (nx/L,ny/L,nz/L)
def write(path,tris):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("wb") as f:
        f.write(b"LEGO 30708 remote plate".ljust(80,b"\0")); f.write(struct.pack("<I",len(tris)))
        for tr in tris:
            n=normal(*tr)
            f.write(struct.pack("<12fH",n[0],n[1],n[2],tr[0][0],tr[0][1],tr[0][2],tr[1][0],tr[1][1],tr[1][2],tr[2][0],tr[2][1],tr[2][2],0))
def pack(items):
    rows=[]; y=MARGIN; placements=[]
    for it in sorted(items,key=lambda q:max(q["w0"],q["h0"],q["w1"],q["h1"]),reverse=True):
        ok=False
        for row in rows:
            for rr in (0,1):
                w=it["w0"] if rr==0 else it["w1"]; h=it["h0"] if rr==0 else it["h1"]
                if h<=row["h"]+1e-6 and row["x"]+w<=BED-MARGIN:
                    placements.append((it,rr,row["x"],row["y"])); row["x"]+=w+SPACING; ok=True; break
            if ok: break
        if ok: continue
        opts=[]
        for rr in (0,1):
            w=it["w0"] if rr==0 else it["w1"]; h=it["h0"] if rr==0 else it["h1"]
            if MARGIN+w<=BED-MARGIN and y+h<=BED-MARGIN: opts.append((h,rr,w,h))
        if not opts: return None
        _,rr,w,h=min(opts); rows.append({"x":MARGIN+w+SPACING,"y":y,"h":h}); placements.append((it,rr,MARGIN,y)); y+=h+SPACING
    return placements
def main():
    by={}
    for p in SRC.rglob("*.stl"):
        m=re.match(r"(.+)_x(\d+)\.stl$",p.name)
        if not m: continue
        part,qty=m.group(1),int(m.group(2)); color=p.parent.name
        t0=norm(read_stl(p)); b0=bbox(t0); t1=rot(t0); b1=bbox(t1)
        for i in range(qty):
            by.setdefault(color,[]).append({"part":part,"copy":i+1,"qty":qty,"t0":t0,"t1":t1,"w0":b0[3]-b0[0],"h0":b0[4]-b0[1],"w1":b1[3]-b1[0],"h1":b1[4]-b1[1]})
    manifest=[]
    for color,items in sorted(by.items()):
        chunks=[items[i:i+MAXN] for i in range(0,len(items),MAXN)]
        for idx,ch in enumerate(chunks,1):
            pl=pack(ch)
            if pl is None:
                raise RuntimeError(f"cannot pack {color} chunk {idx}")
            tris=[]
            for it,rr,x,y in pl:
                tris.extend(trans(it["t0"] if rr==0 else it["t1"],x,y))
                manifest.append([f"{color}_plate_{idx:02d}",color,it["part"],it["copy"],it["qty"],90 if rr else 0,round(x,2),round(y,2)])
            write(OUT/f"{color}_plate_{idx:02d}.stl",tris)
    with (OUT/"PLATE_MAP.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(["plate","colour","part","copy","qty_total","rotation_deg","x_mm","y_mm"]); w.writerows(manifest)
    with zipfile.ZipFile(ROOT/"LEGO_30708_REMOTE_PLATES.zip","w",zipfile.ZIP_DEFLATED) as z:
        for p in OUT.iterdir(): z.write(p,p.name)
    print("remote pieces",len(manifest),"plates",len(list(OUT.glob("*.stl"))))
if __name__=="__main__": main()
