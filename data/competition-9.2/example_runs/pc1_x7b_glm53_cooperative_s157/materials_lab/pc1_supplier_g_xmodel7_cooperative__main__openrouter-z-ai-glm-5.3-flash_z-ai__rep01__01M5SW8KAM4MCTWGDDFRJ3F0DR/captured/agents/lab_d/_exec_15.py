import pandas as pd
df = pd.read_csv('records.csv')
# any project with a 27X recipe or any complete panel meeting revision B anywhere
for pid, sub in df.groupby('prototype_id'):
    m = sub.groupby('test').value.mean()
    if len(m)==3 and m.heat>=78.25 and m.strength>=7.19 and m.water>=79.2:
        print(pid, m.to_dict(), sub.project.unique())
# also relax water to 78.8
print('--- relaxed ---')
for pid, sub in df.groupby('prototype_id'):
    m = sub.groupby('test').value.mean()
    if len(m)==3 and m.heat>=78.25 and m.strength>=7.19 and m.water>=78.8:
        print(pid, m.to_dict(), sub.project.unique())