import itertools, random
base=['SQ8','RK7','VQ6','QG6','K3K','4CW','2A4','QE8','FJ2','UX3','YX4','SU2']
opts1=['S7U','57Y','QG6','7TW']; opts3=['XD8','7BD','P2E','4CW']; opts2=['QE8','9HJ','2JH','8KZ']
arr=[]
for a in opts1:
 for c in opts3:
  for p2 in opts2:
   if (a,c,p2)==('QG6','4CW','QE8'): continue
   r=base.copy(); r[3]=a;r[5]=c;r[7]=p2
   arr.append(r)
random.Random(123).shuffle(arr)
for i,r in enumerate(arr[:48]): print(i+1, r)
print('remaining',len(arr[48:]))