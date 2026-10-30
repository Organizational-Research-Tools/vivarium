import random, itertools
random.seed(1)
mods=[["HP9","V2W","L7A","7FT"],["TN6","T3M","2YJ","38J"],["HD9","PU3","QU7","J9B"],["TE2","G7U","8BE","Q3H"],["9KR","WJ7","42D","2Y6"],["Z2E","2CK","JN6","2CS"],["V9D","Q7N","5JK","8KT"],["4AL","NG4","2FG","9AH"],["V7P","X9S","24J","F2C"],["6XN","83B","6XS","84H"],["A6U","7UX","YS6","3Y7"],["9DA","V8F","G5Y"]]  # conditioning: skip 2JU
recipes=[]
for i in range(48):
    recipes.append([random.choice(m) for m in mods])
for r in recipes: print(r)