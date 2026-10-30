import pandas as pd
df = pd.read_csv('records.csv')
q = df[df.project=='QP-1586']
w = q[(q.test=='wet strength retained')]
print(w[w.value>=79.8][['record_id','kind','prototype_id','measured_by','value']].to_string())
s = q[(q.test=='edge crush resistance') & (q.value>=7.235)]
print(s[['record_id','kind','prototype_id','measured_by','value']].to_string())
h = q[(q.test=='seal hold temperature') & (q.value>=78.625)]
print(h[['record_id','kind','prototype_id','measured_by','value']].to_string())
# and QP-8864
q8 = df[df.project=='QP-8864']
print("---8864---")
print(q8[(q8.test=='wet strength retained')&(q8.value>=79.8)][['record_id','kind','prototype_id','measured_by','value']].to_string())
print(q8[(q8.test=='edge crush resistance')&(q8.value>=7.235)][['record_id','kind','prototype_id','measured_by','value']].to_string())
print(q8[(q8.test=='seal hold temperature')&(q8.value>=78.625)][['record_id','kind','prototype_id','measured_by','value']].to_string())