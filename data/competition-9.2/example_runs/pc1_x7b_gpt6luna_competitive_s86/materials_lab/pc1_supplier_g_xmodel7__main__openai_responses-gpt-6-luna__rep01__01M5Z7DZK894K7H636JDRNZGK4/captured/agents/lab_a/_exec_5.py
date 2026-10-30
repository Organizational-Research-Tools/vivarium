import itertools, json
ap2=['74N','F8Y','EB7','K3K']; ap3=['XD8','7BD','P2E','4CW']; surf=['96Y','T6A','UX3','L2J']
base=['8GP','RK7','YC8','S7U',None,None,'RZ8','9HJ','3XM',None,'JE5','SU2']
combos=[]
for a,b,c in itertools.product(ap2,ap3,surf):
    if (a,b,c)==('EB7','4CW','UX3'): continue
    r=base.copy(); r[4]=a;r[5]=b;r[9]=c;combos.append(r)
print(len(combos));print(json.dumps(combos[:48]));print('---remaining---');print(json.dumps(combos[48:]))