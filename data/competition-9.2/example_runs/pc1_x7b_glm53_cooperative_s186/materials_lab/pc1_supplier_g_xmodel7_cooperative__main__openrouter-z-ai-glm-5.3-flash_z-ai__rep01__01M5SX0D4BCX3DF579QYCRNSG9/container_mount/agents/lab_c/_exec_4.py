import pandas as pd
df = pd.read_csv('records.csv')
mine = df[df['measured_by'].eq('lab_c')]
sub = mine[mine['project'].isin(['QP-4069','QP-1992','QP-4757'])]
print(sub[['record_id','project','prototype_id','test','value','kind','requester']].to_string())
print(sub['kind'].unique())