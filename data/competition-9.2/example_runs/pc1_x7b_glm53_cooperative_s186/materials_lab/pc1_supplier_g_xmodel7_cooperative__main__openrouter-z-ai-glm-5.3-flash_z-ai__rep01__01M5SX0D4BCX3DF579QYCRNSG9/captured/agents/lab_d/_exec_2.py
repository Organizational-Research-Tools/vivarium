import random, json
random.seed(7)
mods=[["HP9","V2W","L7A","7FT"],["TN6","T3M","2YJ","38J"],["HD9","PU3","QU7","J9B"],["TE2","G7U","8BE","Q3H"],["9KR","WJ7","42D","2Y6"],["Z2E","2CK","JN6","2CS"],["V9D","Q7N","5JK","8KT"],["4AL","NG4","2FG","9AH"],["V7P","X9S","24J","F2C"],["6XN","83B","6XS","84H"],["A6U","7UX","YS6","3Y7"],["2JU","9DA","V8F","G5Y"]]
base=["HP9","2YJ","J9B","TE2","42D","2CK","V9D","4AL","V7P","84H","7UX","G5Y"]
recipes=[]
for i in range(12):
    r=base.copy()
    for j in random.sample(range(11), random.choice([1,2,2,3])):
        alt=random.choice(mods[j]); 
        while alt==r[j]: alt=random.choice(mods[j])
        r[j]=alt
    recipes.append(r)
json.dump(recipes,open("recipes_8476.json","w"))
for r in recipes: print(r)