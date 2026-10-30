import pandas as pd
df = pd.read_csv('records.csv')
mine = df[df['measured_by'].eq('lab_c')]
sub = mine[mine['project'].isin(['QP-4069','QP-1992','QP-4757'])]
print(sub.groupby(['project','prototype_id','test','kind']).agg(n=('value','count'),mean=('value','mean')))
print(sub[sub['kind']=='panel'][['record_id','project','prototype_id','test','value']].to_string())
# check who's prototypes these are
print(sub.groupby('prototype_id')[['base_sheet','process_profile_2','additive_package_1','conditioning_step']].first())