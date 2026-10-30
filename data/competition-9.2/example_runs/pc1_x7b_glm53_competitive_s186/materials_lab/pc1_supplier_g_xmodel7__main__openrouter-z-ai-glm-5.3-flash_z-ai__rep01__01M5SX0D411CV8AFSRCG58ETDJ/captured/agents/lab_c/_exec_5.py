import pandas as pd
df=pd.read_csv('records.csv')
# lab_b's QP-3777 strength hits: p_E05X2XJNTY etc
for p in ['p_E05X2XJNTY','p_6HRWVWM6EN','p_MJ6G5J683J','p_E05X2XJNTP']:
    s=df[df.prototype_id==p]
    print(p, s.test.unique(), len(s))
# who else posted? check all prototypes with panels
g=df[df.kind=='qualification'].groupby(['project','prototype_id','test']).agg(n=('value','size'),mean=('value','mean'))
print(g.to_string())