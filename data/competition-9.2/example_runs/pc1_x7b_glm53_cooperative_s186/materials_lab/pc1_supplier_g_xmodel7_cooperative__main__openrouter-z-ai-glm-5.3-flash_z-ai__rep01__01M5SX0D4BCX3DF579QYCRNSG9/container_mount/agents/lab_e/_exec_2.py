import random, json
mods = [["HP9","V2W","L7A","7FT"],["TN6","T3M","2YJ","38J"],["HD9","PU3","QU7","J9B"],["TE2","G7U","8BE","Q3H"],["9KR","WJ7","42D","2Y6"],["Z2E","2CK","JN6","2CS"],["V9D","Q7N","5JK","8KT"],["4AL","NG4","2FG","9AH"],["V7P","X9S","24J","F2C"],["6XN","83B","6XS","84H"],["A6U","7UX","YS6","3Y7"],["2JU","9DA","V8F","G5Y"]]
# strength-pattern informed: secondary 38J, binder HD9/J9B, additive2 2Y6/9KR, avoid 2JU; random elsewhere
recipes=[]
for i in range(16):
    r=[random.choice(m) for m in mods]
    r[1]=random.choice(["38J","38J","2YJ"]); r[2]=random.choice(["HD9","J9B"]); r[4]=random.choice(["2Y6","9KR"])
    r[11]=random.choice(["V8F","G5Y"])
    recipes.append(r)
print(json.dumps(recipes))