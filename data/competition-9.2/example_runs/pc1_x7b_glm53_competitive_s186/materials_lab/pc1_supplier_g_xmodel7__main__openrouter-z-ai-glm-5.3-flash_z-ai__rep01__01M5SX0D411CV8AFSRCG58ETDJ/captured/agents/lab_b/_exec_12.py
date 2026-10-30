import pandas as pd
df = pd.read_csv('records.csv')
for pid in ['p_E05X2XJNTY','p_25SH4G2DQE','p_6HRWVWM6EN','p_V3DS5HS1PT']:
    s=df[df.prototype_id==pid]
    for t in ['seal hold temperature','edge crush resistance','wet strength retained']:
        q=s[(s.test==t)&(s.kind=='qualification')]
        if len(q): print(pid,t,len(q),round(q.value.mean(),4))
