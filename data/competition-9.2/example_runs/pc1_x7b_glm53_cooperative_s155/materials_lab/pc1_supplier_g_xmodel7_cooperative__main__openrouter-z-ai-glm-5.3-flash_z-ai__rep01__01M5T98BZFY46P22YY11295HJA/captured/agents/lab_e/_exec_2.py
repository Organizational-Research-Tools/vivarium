import json
recipes=json.load(open('recipes.json'))
for i,r in enumerate(recipes): print(i,r)