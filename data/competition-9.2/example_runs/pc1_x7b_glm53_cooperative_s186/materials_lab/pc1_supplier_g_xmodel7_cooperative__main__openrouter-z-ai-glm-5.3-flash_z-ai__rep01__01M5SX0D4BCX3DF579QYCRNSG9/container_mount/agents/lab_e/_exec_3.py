import random, json
mods = [["HP9","V2W","L7A","7FT"],["TN6","T3M","2YJ","38J"],["HD9","PU3","QU7","J9B"],["TE2","G7U","8BE","Q3H"],["9KR","WJ7","42D","2Y6"],["Z2E","2CK","JN6","2CS"],["V9D","Q7N","5JK","8KT"],["4AL","NG4","2FG","9AH"],["V7P","X9S","24J","F2C"],["6XN","83B","6XS","84H"],["A6U","7UX","YS6","3Y7"],["2JU","9DA","V8F","G5Y"]]
random.seed(42)
# near-miss backbone variants around p_KC5SYJDEWJ & p_KC5SYJDEWM, plus random strength-focused
recipes=[]
base1=["L7A","38J","HD9","TE2","2Y6","Z2E","5JK","2FG","V7P","83B","3Y7","G5Y"]
base2=["L7A","2YJ","J9B","G7U","9KR","2CK","8KT","NG4","V7P","83B","7UX","V8F"]
for b in (base1,base2):
    for i in range(7):
        r=list(b); m=random.choice(range(11)); r[m]=random.choice(mods[m]) if m!=11 else random.choice(["V8F","G5Y"])
        recipes.append(r)
for i in range(2):
    r=[random.choice(m) for m in mods]; r[11]=random.choice(["V8F","G5Y"]); recipes.append(r)
print(json.dumps(recipes))