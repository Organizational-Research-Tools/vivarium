import pandas as pd
df = pd.read_csv('records.csv')
# my records only (measured_by lab_c or requester lab_c)
mine = df[df['measured_by'].eq('lab_c')]
for proj in ['QP-4069','QP-7006','QP-1992','QP-4152','QP-4757']:
    sub = mine[mine['project']==proj]
    if len(sub)==0:
        print(proj,'no records of mine')
        continue
    g = sub.groupby('prototype_id').agg(n=('value','count'), mean=('value','mean'))
    print('=====',proj)
    print(g)
# also all records on those projects (any lab) to see candidates
print('--- all records on open projects (any lab) ---')
for proj in ['QP-4069','QP-7006','QP-1992','QP-4152','QP-4757']:
    sub = df[df['project']==proj]
    g = sub.groupby(['prototype_id','test']).agg(n=('value','count'), mean=('value','mean'), by=('measured_by','first'))
    print('=====',proj); print(g)