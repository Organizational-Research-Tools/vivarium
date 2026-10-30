import pandas as pd
x=pd.read_csv('records.csv')
z=x[(x.project=='QP-9219') & (x.kind=='qualification')]
for pid,g in z.groupby('prototype_id'):
    props={test: gg.value.mean() for test,gg in g.groupby('instrument') if len(gg)==6}
    if 'strength' in props and props['strength']>7.1984:
        h=x[(x.prototype_id==pid)&(x.instrument=='heat')]
        exp=h[h.kind=='exploratory'].value.mean() if len(h[h.kind=='exploratory']) else None
        hm=h[h.kind=='qualification'].value.mean() if len(h[h.kind=='qualification'])==6 else None
        w=x[(x.prototype_id==pid)&(x.instrument=='water')]
        wexp=w[w.kind=='exploratory'].value.mean() if len(w[w.kind=='exploratory']) else None
        wm=w[w.kind=='qualification'].value.mean() if len(w[w.kind=='qualification'])==6 else None
        print(pid, 'strength',props['strength'],'heat exp/panel',exp,hm,'water exp/panel',wexp,wm)
