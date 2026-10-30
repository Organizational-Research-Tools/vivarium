import pandas as pd
df = pd.read_csv('records.csv')
mods=['base_sheet','secondary_sheet','binder_system','additive_package_1','additive_package_2','additive_package_3','process_profile_1','process_profile_2','process_profile_3','surface_treatment','joint_system','conditioning_step']
for proj in ['QP-4757','QP-7006','QP-4152','QP-8476']:
    q=df[df['project']==proj]
    print('===',proj,len(q))
    best={}
    for pid,sub in q.groupby('prototype_id'):
        quals={t:round(g.value.mean(),2) for t,g in sub[sub.kind=='qualification'].groupby('test')}
        exps={t:round(g.value.mean(),2) for t,g in sub[sub.kind!='qualification'].groupby('test')}
        comp=tuple(sub[mods].dropna(axis=1,how='all').iloc[0].dropna())
        best[pid]=(comp,quals,exps)
    # rank by # tests passing (77.5,7.1,78)
    def npass(a): return sum(1 for t,v in a.items() if (v>=77.5 if t.startswith('seal') else v>=7.1 if t.startswith('edge') else v>=78))
    for pid,(c,qu,ex) in sorted(best.items(), key=lambda kv:-max(npass(kv[1][1]),npass(kv[1][2]))):
        allv={**qu}
        if max(npass(qu),npass(ex))>=2: print(pid,c,'QUAL',qu,'EXP',ex)