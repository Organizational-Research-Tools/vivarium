import pandas as pd
x=pd.read_csv('records.csv')
mods=list(x.columns[11:23])
# grouped unique panels each prot
p=x.groupby(['project','prototype_id','instrument','kind']).agg(mean=('value','mean'),n=('value','size'),measured=('measured_by','first')).reset_index()
print('rows',len(p),'prototypes',x.prototype_id.nunique(),'recipes',x[mods].drop_duplicates().shape[0])
for pr in sorted(x.project.unique()):
 print('\n',pr)
 z=x[x.project==pr].groupby(['prototype_id']+mods).agg(n=('value','size'), mean=('value','mean'), inst=('instrument','first'),by=('measured_by','first')).reset_index()
 for _,r in z.iterrows(): print(r.prototype_id, r.inst, int(r.n),round(r['mean'],5), 'H8Z' if r.base_sheet=='H8Z' else '', ' '.join(str(r[m]) for m in mods))