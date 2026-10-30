base=['SQ8','RK7','VQ6','7TW','K3K','4CW','2A4','8KZ','FJ2','UX3','YX4','SU2']
vars=[['H8Z','8GP','SQ8','QG7'],['5AC','D5U','6TX','RK7'],['VQ6','T5L','YC8','P8G'],['S7U','57Y','QG6','7TW'],['74N','F8Y','EB7','K3K'],['XD8','7BD','P2E','4CW'],['9VQ','2A4','RZ8','H9M'],['QE8','9HJ','2JH','8KZ'],['3XM','E3W','79B','FJ2'],['96Y','T6A','UX3','L2J'],['62B','JE5','YX4','4ZD'],['SU2','6YN','84Z','YT2']]
recipes=[]
for i in range(12):
 for v in vars[i]:
  if v==base[i] or (i==0 and v=='H8Z'): continue
  r=base.copy();r[i]=v;recipes.append(r)
print(len(recipes))
for i,r in enumerate(recipes): print(i+1, r)