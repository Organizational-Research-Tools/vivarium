import pandas as pd
df=pd.read_csv('records.csv')
# strength readings on any QP-5993 prototypes by composition
s=df[(df.test=='edge crush resistance')]
qp=s[s.project=='QP-5993']
print(qp.groupby('prototype_id').agg(n=('value','count'),mean=('value','mean')).sort_values('mean',ascending=False).head(15))
# check composition of p_5JM803X0WS rows
print(df[df.prototype_id=='p_5JM803X0WS'][['record_id','test','value','measured_by','strength' if False else 'secondary_sheet']].head())