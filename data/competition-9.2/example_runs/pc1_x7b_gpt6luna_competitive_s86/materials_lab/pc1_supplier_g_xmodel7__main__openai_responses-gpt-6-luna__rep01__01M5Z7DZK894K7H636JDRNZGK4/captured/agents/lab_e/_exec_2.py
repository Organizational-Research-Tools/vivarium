import random
mods=[['H8Z','8GP','SQ8','QG7'],['5AC','D5U','6TX','RK7'],['VQ6','T5L','YC8','P8G'],['S7U','57Y','QG6','7TW'],['74N','F8Y','EB7','K3K'],['XD8','7BD','P2E','4CW'],['9VQ','2A4','RZ8','H9M'],['QE8','9HJ','2JH','8KZ'],['3XM','E3W','79B','FJ2'],['96Y','T6A','UX3','L2J'],['62B','JE5','YX4','4ZD'],['SU2','6YN','84Z','YT2']]
baseline=['QG7','RK7','P8G','7TW','K3K','7BD','RZ8','2JH','FJ2','L2J','4ZD','SU2']
groups=[[9,6,2],[4,5,9],[0,10,8],[6,3,8],[5,7,3],[1,8,4]] # 0-index
rng=random.Random(924)
recipes=[]
for g in groups:
 for rep in range(8):
  r=baseline.copy()
  for m in g:
   choices=[v for v in mods[m] if not (m==0 and v=='H8Z')]
   r[m]=rng.choice(choices)
  # deduplicate; perturb non-group factors if collision (unlikely)
  while r in recipes:
   m=rng.choice(g)
   choices=[v for v in mods[m] if not (m==0 and v=='H8Z')]
   r[m]=rng.choice(choices)
  recipes.append(r)
print(len(recipes))
for i,r in enumerate(recipes): print(i+1,','.join(r))