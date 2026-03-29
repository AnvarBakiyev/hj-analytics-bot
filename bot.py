import os, requests, json, time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, date

TOKEN = os.environ['BOT_TOKEN']
TG = 'https://api.telegram.org/bot' + TOKEN
HJ = 'https://admin.herosjourney.kz/graphql'
UA = 'HerosJourney/5.4.9 CFNetwork/3826.500.131 Darwin/24.5.0'
states = {}

TYPE_MUSCLE = {
    'push':'Push','pull':'Pull','legs':'Legs','gluteLab':'Glute',
    'fullBody':'Full Body','upperBody':'Upper','bootcamp':'Bootcamp',
    'armBlast':'Arms','metcon':'Metcon'
}
TYPE_LABELS = {
    'push':'Push','pull':'Pull','legs':'Legs','gluteLab':'Glute Lab',
    'fullBody':'Full Body','upperBody':'Upper Body','bootcamp':'Bootcamp',
    'armBlast':'Arm Blast','metcon':'Metcon','assessment':'Assessment'
}
WDO = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
WD_RU = {'Monday':'Пн','Tuesday':'Вт','Wednesday':'Ср','Thursday':'Чт',
          'Friday':'Пт','Saturday':'Сб','Sunday':'Вс'}
WD_FULL = {'Monday':'понедельник','Tuesday':'вторник','Wednesday':'среда',
           'Thursday':'четверг','Friday':'пятница','Saturday':'суббота','Sunday':'воскресенье'}
MUSCLE_GROUPS = ['Push','Pull','Legs','Glute','Full Body','Bootcamp','Arms']

def norm(raw):
    d = ''.join(c for c in raw if c.isdigit())
    if len(d)==11 and d[0]=='8': hj,i = d,'7'+d[1:]
    elif len(d)==11 and d[0]=='7': hj,i = '8'+d[1:],d
    elif len(d)==10: hj,i = '8'+d,'7'+d
    else: hj=i=d
    disp = '+7 ('+i[1:4]+') '+i[4:7]+'-'+i[7:9]+'-'+i[9:11] if (len(i)==11 and i[0]=='7') else '+'+i
    return hj, disp

def tg(m, **k):
    try: return requests.post(TG+'/'+m, json=k, timeout=15).json()
    except: return {}

def send(c, t, **k): return tg('sendMessage', chat_id=c, text=t, parse_mode='HTML', **k)

def sdoc(c, data, fn, cap=''):
    try:
        return requests.post(TG+'/sendDocument',
            data={'chat_id':c,'caption':cap,'parse_mode':'HTML'},
            files={'document':(fn,data,'text/html')}, timeout=120).json()
    except Exception as e: return {'error':str(e)}

def gql(tok, op, q, v=None):
    h = {'accept':'*/*','content-type':'application/json',
         'authorization':'Bearer '+tok,'user-agent':UA}
    try:
        r = requests.post(HJ, headers=h,
            json={'operationName':op,'variables':v or {},'query':q}, timeout=30)
        d = r.json()
        return d.get('data',{}), d.get('errors',[])
    except Exception as e: return {}, [{'message':str(e)}]


def sms(p):
    h = {'accept': '*/*', 'content-type': 'application/json', 'user-agent': UA}
    q = 'mutation getVerificationCode($phoneNumber: String!) { getVerificationCode(phoneNumber: $phoneNumber) { status } }'
    try:
        r = requests.post(HJ, headers=h,
            json={'operationName': 'getVerificationCode', 'variables': {'phoneNumber': p}, 'query': q}, timeout=15)
        result = (r.json().get('data') or {}).get('getVerificationCode', {})
        return result.get('status', '') == 'ok'
    except:
        return False


def vcode(p, c):
    h = {'accept': '*/*', 'content-type': 'application/json', 'user-agent': UA}
    q = 'mutation verifyPhoneNumberWithCode($input: CodeInput!) { verifyPhoneNumberWithCode(input: $input) { status token } }'
    try:
        r = requests.post(HJ, headers=h,
            json={'operationName': 'verifyPhoneNumberWithCode', 'variables': {'input': {'code': c, 'phoneNumber': p}}, 'query': q}, timeout=15)
        res = (r.json().get('data') or {}).get('verifyPhoneNumberWithCode', {})
        return res.get('token', '') if res.get('status') == '200' else None
    except:
        return None
def collect_all_data(tok, uid):
    out = {}

    # ── Layer 1: All bookings (instant) ──
    bd, _ = gql(tok, 'userBookings',
        'query userBookings($userId: ID) { userBookings(userId: $userId) { '
        'id status event { id startTime programSet { name type } trainer { nickname } club { name } } } }',
        {'userId': uid})
    ab = bd.get('userBookings') or []
    out['all_bookings'] = ab

    att_raw = [b for b in ab if b.get('status')=='attended']
    can_raw = [b for b in ab if b.get('status')=='canceled']

    def parse_b(b):
        ev = b.get('event') or {}; ps = ev.get('programSet') or {}
        tr = ev.get('trainer') or {}; cl = ev.get('club') or {}
        s = ev.get('startTime','')
        try:
            dt = datetime.fromisoformat(s.replace('Z','+00:00'))
            return {'date':dt.strftime('%Y-%m-%d'),'month':dt.strftime('%Y-%m'),
                    'wd':dt.strftime('%A'),'h':dt.hour,
                    'prog':ps.get('name',''),'type':ps.get('type',''),
                    'tr':tr.get('nickname',''),'cl':cl.get('name',''),
                    'eid':ev.get('id',''), 'ts': dt.timestamp()}
        except: return None

    att_rows = sorted([r for r in (parse_b(b) for b in att_raw) if r], key=lambda x:x['date'])
    can_rows = [r for r in (parse_b(b) for b in can_raw) if r]
    out['att_rows'] = att_rows
    out['can_rows'] = can_rows

    # ── Layer 2: Monthly tonnage via userBookingsByMonth ──
    monthly_tonnage = {}
    if att_rows:
        start_dt = datetime.strptime(att_rows[0]['month'], '%Y-%m')
        end_dt = datetime.now()
        cur = start_dt
        while cur <= end_dt:
            yr, mo = cur.year, cur.month
            mkey = cur.strftime('%Y-%m')
            md, _ = gql(tok, 'userBookingsByMonth',
                'query userBookingsByMonth($userId: ID!, $year: Int, $month: Int) { '
                'userBookingsByMonth(userId: $userId, year: $year, month: $month) { '
                'id status event { id totalWeight startTime } } }',
                {'userId': uid, 'year': yr, 'month': mo})
            mb = md.get('userBookingsByMonth') or []
            ton = sum(float((b.get('event') or {}).get('totalWeight',0) or 0) for b in mb if b.get('status')=='attended')
            monthly_tonnage[mkey] = round(ton)
            if cur.month == 12: cur = cur.replace(year=cur.year+1, month=1)
            else: cur = cur.replace(month=cur.month+1)
            time.sleep(0.05)
    out['monthly_tonnage'] = monthly_tonnage

    # ── Layer 3: Exercise weights per event (last 60 attended) ──
    recent_att = att_rows[-60:] if len(att_rows) > 60 else att_rows
    ex_sessions = defaultdict(list)

    for row in recent_att:
        eid = row.get('eid','')
        if not eid: continue
        wd, _ = gql(tok, 'eventExerciseWeights',
            'query eventExerciseWeights($userId: ID, $eventId: ID) { '
            'eventExerciseWeights(userId: $userId, eventId: $eventId) { '
            'totalEventWeight '
            'eventExerciseWeight { '
            'stationExercise { exercise { id name } maxWeight } '
            'totalWeight '
            'userExerciseWeights { setNumber weight } } } }',
            {'userId': uid, 'eventId': eid})
        ew = wd.get('eventExerciseWeights') or {}
        total_w = ew.get('totalEventWeight', 0) or 0
        row['event_total_weight'] = round(float(total_w)) if total_w else 0

        for ex_entry in (ew.get('eventExerciseWeight') or []):
            st_ex = ex_entry.get('stationExercise') or {}
            ex_info = st_ex.get('exercise') or {}
            ex_name = ex_info.get('name','')
            if not ex_name: continue
            sets = ex_entry.get('userExerciseWeights') or []
            max_set = max((s.get('weight',0) or 0 for s in sets), default=0)
            if max_set > 0:
                ex_sessions[ex_name].append({'date':row['date'],'weight':float(max_set),'month':row['month']})
        time.sleep(0.08)

    out['ex_sessions'] = dict(ex_sessions)

    # ── Layer 4: Per-event HR+calories (last 30) ──
    hr_by_date = {}
    for row in recent_att[-30:]:
        eid = row.get('eid','')
        if not eid: continue
        pd2, _ = gql(tok, 'postByEventAndUser',
            'query postByEventAndUser($eventId: ID, $userId: ID) { '
            'postByEventAndUser(eventId: $eventId, userId: $userId) { '
            'eventTotalCalories eventAvgHR '
            'eventMaxExerciseWeight { exercise { name } weight } } }',
            {'eventId': eid, 'userId': uid})
        post = pd2.get('postByEventAndUser') or {}
        cal = post.get('eventTotalCalories', 0) or 0
        hr = post.get('eventAvgHR', 0) or 0
        max_ex = post.get('eventMaxExerciseWeight') or {}
        if cal > 0 or hr > 0:
            hr_by_date[row['date']] = {
                'cal': round(float(cal)) if cal else 0,
                'hr': round(float(hr)) if hr else 0,
                'max_ex': (max_ex.get('exercise') or {}).get('name',''),
                'max_ex_w': max_ex.get('weight', 0) or 0
            }
        time.sleep(0.08)

    out['hr_by_date'] = hr_by_date
    return out

def analyse(data):
    ab = data['all_bookings']
    rows = data['att_rows']
    can_rows = data['can_rows']
    ex_sessions = data['ex_sessions']
    monthly_tonnage = data['monthly_tonnage']
    hr_by_date = data['hr_by_date']

    n_att = len(rows); n_can = len(can_rows); total = len(ab)
    ar = round(n_att/total*100,1) if total else 0
    cr = round(n_can/total*100,1) if total else 0

    bm = Counter(r['month'] for r in rows)
    bt = Counter(r['type'] for r in rows if r['type'])
    btr = Counter(r['tr'] for r in rows if r['tr'])
    bwd = Counter(r['wd'] for r in rows)
    bh  = Counter(r['h'] for r in rows)
    ms  = sorted(bm.items())
    wd_vals = [bwd.get(d,0) for d in WDO]
    bmo = max(bm.items(), key=lambda x:x[1]) if bm else ('—',0)
    tt  = btr.most_common(1)[0] if btr else ('—',0)
    ph  = max(bh.items(), key=lambda x:x[1])[0] if bh else 8
    apw = round(n_att/max(len(ms)*4.3,1),1)

    # Muscle balance last 90 days
    cutoff = (datetime.now()-timedelta(days=90)).strftime('%Y-%m-%d')
    mc_90 = Counter(TYPE_MUSCLE.get(r['type'],'Other') for r in rows if r['date']>=cutoff)
    muscle_vals = [mc_90.get(mg,0) for mg in MUSCLE_GROUPS]
    push_cnt = Counter(TYPE_MUSCLE.get(r['type'],'') for r in rows).get('Push',0)
    pull_cnt = Counter(TYPE_MUSCLE.get(r['type'],'') for r in rows).get('Pull',0)

    # Monthly tonnage chart
    ton_months = sorted(monthly_tonnage.items())

    # Exercise analysis — plateaus, progress, trends
    plateaus = []; progressing = []; ex_trends = []
    for ex_name, sessions in ex_sessions.items():
        if len(sessions) < 2: continue
        s_sorted = sorted(sessions, key=lambda x:x['date'])
        dates = [s['date'][5:] for s in s_sorted]
        weights = [s['weight'] for s in s_sorted]
        first_w = weights[0]; last_w = weights[-1]
        max_w = max(weights); prog = round(last_w - first_w, 1)
        n = len(s_sorted)
        if n >= 4:
            ex_trends.append({'name':ex_name,'dates':dates,'weights':weights,
                               'max':max_w,'first':first_w,'last':last_w,'prog':prog,'sessions':n})
        if n >= 5:
            last5 = weights[-5:]
            if max(last5)-min(last5) < 2.5:
                plateaus.append({'name':ex_name,'weight':last5[-1],'sessions':n})
            elif prog > 0:
                progressing.append({'name':ex_name,'gain':prog,'sessions':n})
    ex_trends.sort(key=lambda x:-x['sessions'])
    top_trends = ex_trends[:6]

    # Cancellation DNA
    can_wd = Counter(r['wd'] for r in can_rows if r.get('wd'))
    att_wd = Counter(r['wd'] for r in rows if r.get('wd'))
    can_rate_wd = {}
    for day in WDO:
        tot = att_wd.get(day,0)+can_wd.get(day,0)
        can_rate_wd[day] = round(can_wd.get(day,0)/tot*100) if tot>0 else 0
    can_wd_vals = [can_rate_wd.get(d,0) for d in WDO]
    worst_cd = max(can_rate_wd.items(), key=lambda x:x[1]) if can_rate_wd else ('Monday',0)
    can_type = Counter(r['type'] for r in can_rows if r.get('type'))
    att_type = Counter(r['type'] for r in rows if r.get('type'))
    can_rate_type = {}
    for t in set(list(att_type)+list(can_type)):
        tot = att_type.get(t,0)+can_type.get(t,0)
        can_rate_type[t] = round(can_type.get(t,0)/tot*100) if tot>0 else 0
    can_type_sorted = sorted([(TYPE_LABELS.get(t,t),r) for t,r in can_rate_type.items() if r>0],key=lambda x:-x[1])[:6]

    # HR & calories from real event data
    cal_list = [v['cal'] for v in hr_by_date.values() if v['cal']>0]
    hr_list  = [v['hr']  for v in hr_by_date.values() if v['hr']>0]
    avg_cal = round(sum(cal_list)/len(cal_list)) if cal_list else 0
    avg_hr  = round(sum(hr_list)/len(hr_list))  if hr_list  else 0

    # Tonnage per event trend (last 30 with data)
    ton_events = [(r['date'], r.get('event_total_weight',0))
                  for r in data['att_rows'][-60:] if r.get('event_total_weight',0)>0]
    ton_events.sort(key=lambda x:x[0])

    # Efficiency: % sessions where we recorded weights (shows engagement)
    sessions_with_weights = sum(1 for r in data['att_rows'][-60:] if r.get('event_total_weight',0)>0)
    weight_coverage = round(sessions_with_weights/min(len(data['att_rows']),60)*100) if data['att_rows'] else 0

    # You vs Best You
    now_m = datetime.now().strftime('%Y-%m')
    prev_m = (datetime.now().replace(day=1)-timedelta(days=1)).strftime('%Y-%m')
    cur_mc = bm.get(now_m,0); prev_mc = bm.get(prev_m,0)
    best_ton_month = max(ton_months, key=lambda x:x[1]) if ton_months else ('—',0)
    cur_ton = monthly_tonnage.get(now_m,0)
    avg_ton = round(sum(monthly_tonnage.values())/len(monthly_tonnage)) if monthly_tonnage else 0

    # Top records this period
    max_w_overall = max((s['weight'] for ss in ex_sessions.values() for s in ss), default=0)
    max_w_ex = ''
    for ex_name, sessions in ex_sessions.items():
        if sessions and max(s['weight'] for s in sessions) == max_w_overall:
            max_w_ex = ex_name; break

    return {
        'n_att':n_att,'n_can':n_can,'total':total,'ar':ar,'cr':cr,
        'ms':ms,'bmo':bmo,'tt':tt,'ph':ph,'apw':apw,
        'wd_vals':wd_vals,'bt':bt,'btr':btr,'muscle_vals':muscle_vals,
        'push_cnt':push_cnt,'pull_cnt':pull_cnt,
        'ton_months':ton_months,'ton_events':ton_events,
        'plateaus':plateaus,'progressing':progressing,'top_trends':top_trends,'ex_trends':ex_trends,
        'can_wd_vals':can_wd_vals,'worst_cd':worst_cd,'can_type_sorted':can_type_sorted,
        'avg_cal':avg_cal,'avg_hr':avg_hr,'hr_by_date':hr_by_date,
        'cur_mc':cur_mc,'prev_mc':prev_mc,'best_ton_month':best_ton_month,
        'cur_ton':cur_ton,'avg_ton':avg_ton,'weight_coverage':weight_coverage,
        'max_w_overall':max_w_overall,'max_w_ex':max_w_ex,
    }

def coach_letter(nick, a):
    n_att=a['n_att']; n_m=len(a['ms']); ar=a['ar']; cr=a['cr']
    push=a['push_cnt']; pull=a['pull_cnt']; plateaus=a['plateaus']
    worst_cd=a['worst_cd']; apw=a['apw']; bmo=a['bmo']
    avg_cal=a['avg_cal']; max_w=a['max_w_overall']; max_w_ex=a['max_w_ex']
    prog=a['progressing']

    p = []
    p.append('<p><b>' + nick + '</b>, вот данные которых нет в приложении — только честные цифры.</p>')

    if ar >= 75:
        p.append('<p>🏆 <b>Посещаемость ' + str(ar) + '%</b> — это топ-уровень. Большинство пользователей не дотягивают до 60%. Такая регулярность — твоё главное преимущество.</p>')
    elif ar >= 55:
        p.append('<p>📊 <b>Посещаемость ' + str(ar) + '%</b> — хорошо, но есть потенциал. Ещё 1-2 тренировки в неделю без отмен дадут ощутимый прирост.</p>')
    else:
        p.append('<p>⚠️ <b>Посещаемость ' + str(ar) + '%</b> — главный тормоз прогресса прямо сейчас. Тело растёт от системы, а не от разовых усилий.</p>')

    if push > 0 and pull > 0:
        ratio = round(push/pull, 1)
        if ratio > 1.35:
            p.append('<p>🔴 <b>Push/Pull дисбаланс ' + str(ratio) + ':1</b> — ' + str(push) + ' Push против ' + str(pull) + ' Pull. Риск импинджмента плеча и нарушения осанки. Добавь Pull-день.</p>')
        elif ratio <= 1.15:
            p.append('<p>✅ <b>Push/Pull баланс отличный</b>: ' + str(push) + ' vs ' + str(pull) + '. Спина и грудь развиваются равномерно.</p>')
        else:
            p.append('<p>🟡 <b>Лёгкий перекос в Push</b> (' + str(push) + ' vs ' + str(pull) + '). Держи под контролем.</p>')

    if plateaus:
        names = ', '.join(pl['name'][:20] for pl in plateaus[:3])
        p.append('<p>🔴 <b>Плато на ' + str(len(plateaus)) + ' упражнениях</b>: ' + names + '. Вес не менялся 5+ сессий подряд — нужен +2.5 кг на следующей тренировке. Иначе адаптация остановилась.</p>')
    elif len(prog) >= 3:
        top_g = sorted(prog, key=lambda x:-x['gain'])[:2]
        gains = ', '.join(x['name'][:18]+' +'+str(x['gain'])+' кг' for x in top_g)
        p.append('<p>📈 <b>Реальный прогресс в силе</b>: ' + gains + '. Прогрессивная перегрузка работает — продолжай фиксировать веса.</p>')

    if worst_cd[1] > 40:
        dn = WD_FULL.get(worst_cd[0], worst_cd[0]).capitalize()
        p.append('<p>⚠️ <b>' + dn + ' — твой проблемный день</b>: ' + str(worst_cd[1]) + '% записей не случаются. Или не планируй на этот день, или убери всё что мешает.</p>')

    if avg_cal > 0:
        if avg_cal >= 600:
            p.append('<p>🔥 <b>' + str(avg_cal) + ' ккал за тренировку</b> — высокая интенсивность. Убедись что питание покрывает расход.</p>')
        else:
            p.append('<p>💡 <b>' + str(avg_cal) + ' ккал за тренировку</b> — есть запас по интенсивности. Сокращение отдыха между сетами поднимет и этот показатель, и результат.</p>')

    if max_w > 0 and max_w_ex:
        p.append('<p>💪 <b>Рекорд: ' + str(max_w) + ' кг</b> — ' + max_w_ex[:30] + '. Следующая цель: побить это.</p>')

    p.append('<p>📌 Рекорд активности: <b>' + bmo[0] + ' — ' + str(bmo[1]) + ' тренировок</b>. ')
    if a['cur_mc'] >= bmo[1]:
        p[-1] += 'Этот месяц уже на уровне рекорда — дожми! 🔥</p>'
    else:
        rem = bmo[1] - a['cur_mc']
        p[-1] += 'До рекорда осталось ' + str(rem) + ' тренировок в этом месяце.</p>'

    p.append('<p>➡️ <b>Одно действие прямо сейчас:</b> ')
    if plateaus:
        p[-1] += '+2.5 кг на ' + plateaus[0]['name'][:25] + ' на следующей тренировке.</p>'
    elif push > pull * 1.3:
        p[-1] += 'Записаться на Pull прямо сейчас.</p>'
    elif ar < 60:
        p[-1] += '3 тренировки следующей недели — без отмен, просто три.</p>'
    else:
        p[-1] += 'Побить рекорд: ' + str(bmo[1]) + ' тренировок в месяц.</p>'

    return '\n'.join(p)

def render_html(nick, lvl, cl_, hp_name, hpl, hpf, fw, lw, gd, a):
    def jd(x): return json.dumps(x, ensure_ascii=False)

    n_att=a['n_att']; n_can=a['n_can']; total=a['total']
    ar=a['ar']; cr=a['cr']; apw=a['apw']
    ms=a['ms']; bmo=a['bmo']; tt=a['tt']
    gr = 'A' if ar>=80 else 'B+' if ar>=65 else 'B' if ar>=55 else 'C+'

    tbars = ''
    if a['btr']:
        mx = a['btr'].most_common(1)[0][1]
        for t, c in a['btr'].most_common(7):
            p = round(c/mx*100)
            tbars += ('<div style="display:flex;align-items:center;gap:10px;margin-bottom:9px">'
                      '<div style="font-size:12px;font-weight:600;width:105px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis">' + t + '</div>'
                      '<div style="flex:1;height:6px;background:#e8e4dd;border-radius:3px;overflow:hidden">'
                      '<div style="height:100%;width:' + str(p) + '%;background:linear-gradient(90deg,#2d5a27,#88c97e);border-radius:3px"></div></div>'
                      '<div style="font-size:12px;font-weight:700;color:#2d5a27;width:24px;text-align:right">' + str(c) + '</div></div>')

    plateau_html = ''
    for pl in a['plateaus'][:6]:
        plateau_html += ('<div style="display:flex;align-items:center;gap:12px;padding:10px 14px;'
                         'background:#fdf2f1;border:1px solid #f5c6c3;border-radius:10px;margin-bottom:8px">'
                         '<div style="font-size:16px">🔴</div>'
                         '<div style="flex:1"><div style="font-size:13px;font-weight:600">' + pl['name'] + '</div>'
                         '<div style="font-size:11px;color:#888">' + str(pl['weight']) + ' кг · ' + str(pl['sessions']) + ' сессий без изменений</div></div>'
                         '<div style="font-size:11px;font-weight:700;color:#c0392b;padding:3px 8px;background:#fff0ee;border:1px solid #fcc;border-radius:6px">ПЛАТО</div></div>')
    for pg in sorted(a['progressing'], key=lambda x:-x['gain'])[:5]:
        plateau_html += ('<div style="display:flex;align-items:center;gap:12px;padding:10px 14px;'
                         'background:#edf7f0;border:1px solid #c3e6cc;border-radius:10px;margin-bottom:8px">'
                         '<div style="font-size:16px">📈</div>'
                         '<div style="flex:1"><div style="font-size:13px;font-weight:600">' + pg['name'] + '</div>'
                         '<div style="font-size:11px;color:#888">прогресс +' + str(pg['gain']) + ' кг за все сессии · ' + str(pg['sessions']) + ' сессий</div></div>'
                         '<div style="font-size:11px;font-weight:700;color:#2d7d46;padding:3px 8px;background:#e8f5ea;border:1px solid #c3e6cc;border-radius:6px">РОСТ ↑</div></div>')
    if not plateau_html:
        plateau_html = '<div style="text-align:center;padding:20px;color:#888;font-size:13px">Недостаточно данных — записывай веса на тренировках</div>'

    TC = ['#f5a623','#4ade80','#60a5fa','#c084fc','#f87171','#fbbf24']
    trend_cards = ''
    for i, ex in enumerate(a['top_trends']):
        pc = '#2d7d46' if ex['prog']>0 else ('#c0392b' if ex['prog']<0 else '#888')
        ps = ('+' if ex['prog']>0 else '') + str(ex['prog']) + ' кг'
        trend_cards += ('<div style="background:#fff;border-radius:13px;box-shadow:0 2px 12px rgba(0,0,0,.05);border:1px solid #ede9e0;padding:14px">'
                        '<div style="font-size:12px;font-weight:700;margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + ex['name'] + '</div>'
                        '<div style="display:flex;justify-content:space-between;font-size:11px;color:#999;margin-bottom:10px">'
                        '<span>' + str(ex['sessions']) + ' сессий</span>'
                        '<span style="font-weight:700;color:' + pc + '">' + ps + '</span></div>'
                        '<div style="position:relative;height:90px"><canvas id="tr' + str(i) + '"></canvas></div>'
                        '<div style="display:flex;justify-content:space-between;font-size:10px;color:#aaa;margin-top:6px">'
                        '<span>' + str(ex['first']) + ' кг</span><span>макс: ' + str(ex['max']) + ' кг</span></div></div>')

    yvby = ''
    now_m = a.get('cur_mc',0); best_m = a['bmo'][1]
    best_ton = a['best_ton_month']; cur_ton = a['cur_ton']; avg_ton = a['avg_ton']
    comps = [
        ('Тренировок в этом месяце', str(now_m), str(best_m)+' (рекорд)', now_m >= best_m*0.8),
        ('Тоннаж в этом месяце, кг', str(cur_ton), str(best_ton[1])+' (рекорд: '+best_ton[0]+')', cur_ton >= best_ton[1]*0.75 if best_ton[1]>0 else False),
        ('Средний тоннаж/мес., кг', str(avg_ton), str(best_ton[1]), cur_ton >= avg_ton),
        ('Тренировок в неделю', str(a['apw']), '3.0+', a['apw']>=3.0),
        ('Посещаемость', str(ar)+'%', '80%', ar>=75),
    ]
    for label, cur, best, good in comps:
        col = '#2d7d46' if good else '#c0392b'; ico = '✅' if good else '🎯'
        yvby += ('<div style="display:flex;align-items:center;justify-content:space-between;'
                 'padding:12px 16px;background:#f8f7f3;border-radius:10px;margin-bottom:8px">'
                 '<div style="font-size:12px;color:#666">' + label + '</div>'
                 '<div style="display:flex;align-items:center;gap:18px">'
                 '<div style="text-align:center"><div style="font-size:18px;font-weight:800;color:' + col + '">' + cur + '</div>'
                 '<div style="font-size:10px;color:#aaa">сейчас</div></div>'
                 '<div style="font-size:18px">' + ico + '</div>'
                 '<div style="text-align:center"><div style="font-size:18px;font-weight:800;color:#2d5a27">' + best + '</div>'
                 '<div style="font-size:10px;color:#aaa">цель</div></div>'
                 '</div></div>')

    hr_dates = sorted(a['hr_by_date'].keys())[-20:]
    hr_cal_data = [a['hr_by_date'][d]['cal'] for d in hr_dates]
    hr_hr_data  = [a['hr_by_date'][d]['hr']  for d in hr_dates]
    hr_labels   = [d[5:] for d in hr_dates]

    tr_html = ''
    for r in reversed(a.get('att_rows',[])[-50:]):
        tw = r.get('event_total_weight',0)
        tw_str = str(tw)+' кг' if tw else '—'
        tr_html += ('<tr><td style="white-space:nowrap">' + r['date'] + '</td>'
                    '<td>' + r['prog'] + '</td><td>' + r['tr'] + '</td>'
                    '<td style="font-weight:600;color:#2d5a27">' + tw_str + '</td>'
                    '<td style="color:#888">' + r['cl'] + '</td></tr>')

    css = []
    css.append('@import url(https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap);')
    css.append('*{box-sizing:border-box;margin:0;padding:0}')
    css.append('body{background:#f4f3ef;color:#1a1a1a;font-family:Inter,-apple-system,sans-serif;line-height:1.6}')
    css.append('.hero{background:linear-gradient(135deg,#0c1a0a 0%,#1a3318 45%,#2d5a27 100%);color:#fff;padding:52px 0 72px;position:relative;overflow:hidden}')
    css.append('.hero::before{content:"";position:absolute;top:-25%;right:-8%;width:500px;height:500px;background:radial-gradient(circle,rgba(168,217,160,.07),transparent 65%);border-radius:50%}')
    css.append('.inner,.wrap{max-width:960px;margin:0 auto;padding:0 28px;position:relative}')
    css.append('.hero-badge{display:inline-flex;align-items:center;gap:6px;background:rgba(168,217,160,.14);border:1px solid rgba(168,217,160,.28);border-radius:100px;padding:5px 16px;font-size:12px;font-weight:600;margin-bottom:18px;color:#a8d9a0;letter-spacing:.2px}')
    css.append('.hero h1{font-size:38px;font-weight:900;line-height:1.13;margin-bottom:8px;letter-spacing:-.6px}')
    css.append('.hero h1 .name{color:#a8d9a0}')
    css.append('.hero-sub{font-size:13px;color:rgba(255,255,255,.5);margin-bottom:28px}')
    css.append('.hs{display:flex;gap:32px;flex-wrap:wrap}')
    css.append('.hs-v{font-size:26px;font-weight:800;color:#a8d9a0;line-height:1}.hs-l{font-size:10px;color:rgba(255,255,255,.45);margin-top:4px;text-transform:uppercase;letter-spacing:.6px}')
    css.append('.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-top:-42px}')
    css.append('.kpi{background:#fff;border-radius:14px;box-shadow:0 8px 32px rgba(0,0,0,.10);border:1px solid #ede9e0;padding:18px 14px}')
    css.append('.ki{font-size:20px;margin-bottom:7px}.kv{font-size:22px;font-weight:800;line-height:1;margin-bottom:2px}.kl{font-size:10px;color:#999;text-transform:uppercase;letter-spacing:.4px;font-weight:600}.ks{font-size:10px;color:#bbb;margin-top:2px}')
    css.append('.coach-wrap{background:#fff;border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,.06);border-left:5px solid #2d5a27;padding:28px 32px}')
    css.append('.coach-lbl{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:2px;color:#2d5a27;margin-bottom:12px}')
    css.append('.coach-wrap p{font-size:14px;line-height:1.82;margin-bottom:10px;color:#2a2a2a}.coach-wrap p:last-child{margin-bottom:0}')
    css.append('.sec{padding:30px 0 0}.sl{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:2px;color:#2d5a27;margin-bottom:6px}')
    css.append('.st{font-size:22px;font-weight:800;letter-spacing:-.3px;margin-bottom:4px}.ss{font-size:12px;color:#999;margin-bottom:20px}')
    css.append('.card{background:#fff;border-radius:14px;box-shadow:0 2px 18px rgba(0,0,0,.05);border:1px solid #ede9e0;padding:20px}')
    css.append('.g2{display:grid;grid-template-columns:1fr 1fr;gap:16px}.g3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px}')
    css.append('.tgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}')
    css.append('.ct{font-size:13px;font-weight:700;margin-bottom:2px}.cs{font-size:11px;color:#999;margin-bottom:12px}')
    css.append('.cw{position:relative}.tw{overflow-x:auto}')
    css.append('table{width:100%;border-collapse:collapse;font-size:12px}')
    css.append('th{text-align:left;padding:9px 12px;color:#999;font-weight:600;text-transform:uppercase;font-size:10px;letter-spacing:.4px;border-bottom:2px solid #ede9e0}')
    css.append('td{padding:10px 12px;border-bottom:1px solid #f0ece6}tr:hover td{background:#fafaf7}')
    css.append('.hp-bar{background:#edf7f0;border:1px solid #c3e6cc;border-radius:12px;padding:14px 18px;display:flex;align-items:center;gap:14px}')
    css.append('.footer{margin-top:48px;padding:22px 0;border-top:1px solid #ede9e0;text-align:center;color:#bbb;font-size:11px}')
    css.append('.stat-big{text-align:center;padding:20px 14px;background:#f8f7f3;border-radius:12px}')
    css.append('.stat-big .sv{font-size:36px;font-weight:900;line-height:1}.stat-big .sl2{font-size:11px;color:#999;margin-top:4px}')
    css.append('@media(max-width:760px){.kpis,.g2,.g3,.tgrid{grid-template-columns:1fr 1fr}.hero h1{font-size:26px}.inner,.wrap{padding:0 16px}}')
    css.append('@media(max-width:480px){.kpis{grid-template-columns:1fr 1fr}}')

    h = []
    h.append('<!DOCTYPE html><html lang="ru"><head>')
    h.append('<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">')
    h.append('<title>' + nick + ' · HJ Analytics</title>')
    h.append('<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>')
    h.append('<style>' + '\n'.join(css) + '</style></head><body>')

    h.append('<div class="hero"><div class="inner">')
    h.append('<div class="hero-badge">⚔️ Hero\'s Journey · Premium Аналитика</div>')
    h.append('<h1>Твои тренировки,<br><span class="name">' + nick + '</span></h1>')
    h.append('<p class="hero-sub">' + lvl + ' · ' + cl_ + ' · ' + fw + ' — ' + lw + '</p>')
    h.append('<div class="hs">')
    h.append('<div><div class="hs-v">' + str(n_att) + '</div><div class="hs-l">тренировок</div></div>')
    h.append('<div><div class="hs-v">' + str(len(ms)) + '</div><div class="hs-l">месяцев</div></div>')
    h.append('<div><div class="hs-v">' + str(ar) + '%</div><div class="hs-l">посещаемость</div></div>')
    h.append('<div><div class="hs-v">' + str(a['avg_cal'] or '—') + '</div><div class="hs-l">ккал/трен.</div></div>')
    h.append('<div><div class="hs-v">' + gr + '</div><div class="hs-l">оценка</div></div>')
    h.append('</div></div></div>')

    h.append('<div class="wrap">')
    h.append('<div class="kpis">')
    h.append('<div class="kpi"><div class="ki">📅</div><div class="kv">' + str(apw) + '</div><div class="kl">трен./нед.</div></div>')
    h.append('<div class="kpi"><div class="ki">🏆</div><div class="kv">' + str(bmo[1]) + '</div><div class="kl">лучший месяц</div><div class="ks">' + bmo[0] + '</div></div>')
    h.append('<div class="kpi"><div class="ki">❌</div><div class="kv">' + str(cr) + '%</div><div class="kl">отмен</div><div class="ks">' + str(n_can) + ' из ' + str(total) + '</div></div>')
    h.append('<div class="kpi"><div class="ki">🤝</div><div class="kv">' + str(tt[1]) + '</div><div class="kl">' + tt[0][:12] + '</div><div class="ks">топ тренер</div></div>')
    h.append('<div class="kpi"><div class="ki">💪</div><div class="kv">' + str(a['max_w_overall']) + '</div><div class="kl">рекорд кг</div><div class="ks">' + a['max_w_ex'][:14] + '</div></div>')
    h.append('</div>')

    h.append('<div style="padding-top:22px"><div class="hp-bar"><div style="font-size:24px">🎫</div><div>')
    h.append('<div style="font-size:14px;font-weight:700">' + hp_name + '</div>')
    h.append('<div style="font-size:12px;color:#888">Визитов: <b style="color:#2d5a27">' + str(hpl) + '</b> · До: <b>' + hpf + '</b></div>')
    h.append('</div></div></div>')

    h.append('<div class="sec"><div class="sl">Разбор</div><div class="st">Анализ от фитнес-аналитика</div>')
    h.append('<div class="coach-wrap"><div class="coach-lbl">💬 Данных нет в приложении</div>' + coach_letter(nick, a) + '</div></div>')

    h.append('<div class="sec"><div class="sl">01 — Тоннаж</div><div class="st">Сколько железа ты поднял</div><div class="ss">Суммарный вес за каждый месяц · Динамика нагрузки по тренировкам</div>')
    h.append('<div class="g2">')
    ton_m_labels = jd([t[0] for t in a['ton_months']]); ton_m_vals = jd([t[1] for t in a['ton_months']])
    h.append('<div class="card"><div class="ct">Тоннаж по месяцам (кг)</div><div class="cs">Реальный суммарный вес за каждый месяц</div><div class="cw" style="height:220px"><canvas id="cTon"></canvas></div></div>')
    ton_ev_labels = jd([t[0][5:] for t in a['ton_events']])
    ton_ev_vals   = jd([t[1] for t in a['ton_events']])
    h.append('<div class="card"><div class="ct">Тоннаж за тренировку (кг)</div><div class="cs">Последние ' + str(len(a['ton_events'])) + ' тренировок с данными</div><div class="cw" style="height:220px"><canvas id="cTonEv"></canvas></div></div>')
    h.append('</div></div>')

    h.append('<div class="sec"><div class="sl">02 — Активность</div><div class="st">Динамика посещений и баланс нагрузок</div><div class="ss">Тренировки по месяцам · Баланс мышечных групп за 90 дней</div>')
    h.append('<div class="g2">')
    mv = [m[1] for m in ms]
    m_labels = jd([m[0] for m in ms]); m_vals = jd(mv)
    h.append('<div class="card"><div class="ct">Тренировок по месяцам</div><div class="cs">Количество посещённых занятий</div><div class="cw" style="height:210px"><canvas id="cMonth"></canvas></div></div>')
    h.append('<div class="card"><div class="ct">Баланс мышечных групп (90 дней)</div><div class="cs">Радар должен быть округлым — дисбаланс виден сразу</div><div class="cw" style="height:210px"><canvas id="cRadar"></canvas></div></div>')
    h.append('</div></div>')

    h.append('<div class="sec"><div class="sl">03 — Плато и прогресс</div><div class="st">Что растёт, что застряло</div><div class="ss">Анализ на основе реальных весов по каждой тренировке</div>')
    h.append('<div class="card">' + plateau_html + '</div></div>')

    if a['top_trends']:
        h.append('<div class="sec"><div class="sl">04 — Динамика весов</div><div class="st">Тренды по упражнениям</div><div class="ss">Каждая точка — реальная сессия · Видно плато, рекорды, спады</div>')
        h.append('<div class="tgrid">' + trend_cards + '</div></div>')

    h.append('<div class="sec"><div class="sl">05 — Структура</div><div class="st">Типы нагрузок · Дни · Тренеры</div><div class="ss">Состав твоей программы</div>')
    h.append('<div class="g3">')
    type_top = a['bt'].most_common(7)
    h.append('<div class="card"><div class="ct">Типы тренировок</div><div class="cs">Доли программ</div><div class="cw" style="height:195px"><canvas id="cType"></canvas></div></div>')
    wd_v = jd(a['wd_vals'])
    h.append('<div class="card"><div class="ct">По дням недели</div><div class="cs">Когда тренируешься чаще</div><div class="cw" style="height:195px"><canvas id="cWd"></canvas></div></div>')
    h.append('<div class="card"><div class="ct">Топ тренеров</div><div class="cs">Совместных занятий</div><div style="padding-top:4px">' + tbars + '</div></div>')
    h.append('</div></div>')

    h.append('<div class="sec"><div class="sl">06 — ДНК отмен</div><div class="st">Когда и что ты срываешь</div><div class="ss">Процент отмен по дням и типам — паттерны которые ты не замечаешь</div>')
    h.append('<div class="g2">')
    can_wd_v = jd(a['can_wd_vals'])
    h.append('<div class="card"><div class="ct">% отмен по дням недели</div><div class="cs">Красный — твой проблемный день</div><div class="cw" style="height:195px"><canvas id="cCanWd"></canvas></div></div>')
    h.append('<div class="card"><div class="ct">% отмен по типу тренировки</div><div class="cs">Что чаще всего срывается</div><div class="cw" style="height:195px"><canvas id="cCanType"></canvas></div></div>')
    h.append('</div></div>')

    if a['avg_cal'] > 0 or a['avg_hr'] > 0:
        h.append('<div class="sec"><div class="sl">07 — Эффективность</div><div class="st">Калории и пульс по тренировкам</div><div class="ss">Данные из системы отслеживания Hero\'s Journey</div>')
        h.append('<div class="g2">')
        h.append('<div class="card">')
        h.append('<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">')
        cal_col = '#c8512a' if a['avg_cal']>=600 else '#f5a623'
        hr_col = '#c0392b' if a['avg_hr']>=160 else '#1e4d8c'
        h.append('<div class="stat-big"><div class="sv" style="color:' + cal_col + '">' + str(a['avg_cal']) + '</div><div class="sl2">ккал / тренировка</div></div>')
        h.append('<div class="stat-big"><div class="sv" style="color:' + hr_col + '">' + str(a['avg_hr']) + '</div><div class="sl2">bpm средний пульс</div></div>')
        h.append('</div>')
        if hr_cal_data and any(v > 0 for v in hr_cal_data):
            h.append('<div class="ct">Калории по тренировкам</div><div class="cs">Последние занятия</div>')
            h.append('<div class="cw" style="height:120px"><canvas id="cCal"></canvas></div>')
        h.append('</div>')
        h.append('<div class="card"><div class="ct">Ты vs Лучший ты</div><div class="cs">Текущие показатели vs личные рекорды</div>' + yvby + '</div>')
        h.append('</div></div>')
    else:
        sn = '07'
        h.append('<div class="sec"><div class="sl">' + sn + ' — Ты vs Лучший ты</div><div class="st">Текущие показатели vs рекорды</div>')
        h.append('<div class="card">' + yvby + '</div></div>')

    sn_last = '08' if (a['avg_cal']>0 or a['avg_hr']>0) else '08'
    h.append('<div class="sec"><div class="sl">' + sn_last + ' — История</div><div class="st">Последние 50 тренировок</div>')
    h.append('<div class="card"><div class="tw"><table><thead><tr><th>Дата</th><th>Программа</th><th>Тренер</th><th>Тоннаж</th><th>Клуб</th></tr></thead>')
    h.append('<tbody>' + tr_html + '</tbody></table></div></div></div>')
    h.append('</div>')
    h.append('<div class="footer"><div class="wrap">Отчёт ' + gd + ' · HJ Analytics Premium · ' + str(n_att) + ' тренировок<br>Аналитика недоступна в приложении Hero\'s Journey</div></div>')

    h.append('<script>Chart.defaults.font.family="Inter,sans-serif";Chart.defaults.color="#999";')

    tv = jd([t[1] for t in a['ton_months']])
    h.append('var tv=' + tv + ';')
    h.append('new Chart(document.getElementById("cTon"),{type:"bar",data:{labels:' + ton_m_labels + ',datasets:[{data:tv,backgroundColor:tv.map(function(v){return v==Math.max.apply(null,tv)?"#c8512a":"#f5c6a8";}),borderRadius:6,borderSkipped:false}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{display:false},ticks:{maxRotation:45,font:{size:10}}},y:{grid:{color:"#ede9e0"},ticks:{callback:function(v){return (v/1000).toFixed(0)+"t";}}}}}});')
    if a['ton_events']:
        h.append('new Chart(document.getElementById("cTonEv"),{type:"line",data:{labels:' + ton_ev_labels + ',datasets:[{data:' + ton_ev_vals + ',borderColor:"#c8512a",backgroundColor:"rgba(200,81,42,0.08)",borderWidth:2.5,pointRadius:2,fill:true,tension:0.35}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{display:false},ticks:{maxTicksLimit:8,font:{size:10}}},y:{grid:{color:"#ede9e0"}}}}});')

    h.append('var mv=' + m_vals + ';')
    h.append('new Chart(document.getElementById("cMonth"),{type:"bar",data:{labels:' + m_labels + ',datasets:[{data:mv,backgroundColor:mv.map(function(v){return v==Math.max.apply(null,mv)?"#2d5a27":"#a8d9a0";}),borderRadius:6,borderSkipped:false}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{display:false},ticks:{maxRotation:45,font:{size:10}}},y:{grid:{color:"#ede9e0"}}}}});')
    h.append('new Chart(document.getElementById("cRadar"),{type:"radar",data:{labels:' + jd(MUSCLE_GROUPS) + ',datasets:[{data:' + jd(a['muscle_vals']) + ',backgroundColor:"rgba(45,90,39,0.13)",borderColor:"#2d5a27",borderWidth:2.5,pointBackgroundColor:"#2d5a27",pointRadius:4}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{r:{grid:{color:"#e8e4dd"},ticks:{display:false},pointLabels:{font:{size:10}}}}}});')
    h.append('new Chart(document.getElementById("cType"),{type:"doughnut",data:{labels:' + jd([TYPE_LABELS.get(k,k) for k,_ in type_top]) + ',datasets:[{data:' + jd([v for _,v in type_top]) + ',backgroundColor:["#2d5a27","#88c97e","#c8512a","#f5a623","#1e4d8c","#60a5fa","#c084fc"],borderWidth:3,borderColor:"#fff"}]},options:{responsive:true,maintainAspectRatio:false,cutout:"55%",plugins:{legend:{position:"right",labels:{font:{size:10},boxWidth:10}}}}});')
    h.append('var wv=' + wd_v + ';')
    h.append('new Chart(document.getElementById("cWd"),{type:"bar",data:{labels:' + jd([WD_RU.get(d,d) for d in WDO]) + ',datasets:[{data:wv,backgroundColor:wv.map(function(v){return v==Math.max.apply(null,wv)?"#2d5a27":"#d4e8d1";}),borderRadius:6,borderSkipped:false}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{display:false}},y:{grid:{color:"#ede9e0"}}}}});')
    h.append('var cw=' + can_wd_v + ';')
    h.append('new Chart(document.getElementById("cCanWd"),{type:"bar",data:{labels:' + jd([WD_RU.get(d,d) for d in WDO]) + ',datasets:[{data:cw,backgroundColor:cw.map(function(v){return v==Math.max.apply(null,cw)?"#c0392b":"#f5c6c3";}),borderRadius:6,borderSkipped:false}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:function(c){return c.raw+"%";}}}},scales:{x:{grid:{display:false}},y:{grid:{color:"#ede9e0"},ticks:{callback:function(v){return v+"%";}}}}}});')
    h.append('new Chart(document.getElementById("cCanType"),{type:"bar",data:{labels:' + jd([x[0] for x in a['can_type_sorted']]) + ',datasets:[{data:' + jd([x[1] for x in a['can_type_sorted']]) + ',backgroundColor:"#f87171",borderRadius:6,borderSkipped:false}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:function(c){return c.raw+"%";}}}},scales:{x:{grid:{display:false},ticks:{maxRotation:30,font:{size:10}}},y:{grid:{color:"#ede9e0"},ticks:{callback:function(v){return v+"%";}}}}}});')

    if hr_cal_data and any(v > 0 for v in hr_cal_data):
        h.append('new Chart(document.getElementById("cCal"),{type:"line",data:{labels:' + jd(hr_labels) + ',datasets:[{data:' + jd(hr_cal_data) + ',borderColor:"#c8512a",backgroundColor:"rgba(200,81,42,0.08)",borderWidth:2,pointRadius:2,fill:true,tension:0.3}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{display:false},ticks:{font:{size:10}}},y:{grid:{color:"#ede9e0"}}}}});')

    TC = ['#f5a623','#4ade80','#60a5fa','#c084fc','#f87171','#fbbf24']
    h.append('var TRENDS=' + jd(a['top_trends']) + ';')
    h.append('var TC=' + jd(TC) + ';')
    h.append('TRENDS.forEach(function(ex,i){')
    h.append('  var cv=document.getElementById("tr"+i); if(!cv) return;')
    h.append('  var grd=cv.getContext("2d").createLinearGradient(0,0,0,90);')
    h.append('  grd.addColorStop(0,TC[i]+"30"); grd.addColorStop(1,TC[i]+"00");')
    h.append('  new Chart(cv,{type:"line",data:{labels:ex.dates,datasets:[{data:ex.weights,')
    h.append('    borderColor:TC[i],backgroundColor:grd,borderWidth:2.5,')
    h.append('    pointRadius:ex.dates.length>15?1:3,pointHoverRadius:5,fill:true,tension:0.3}]},')
    h.append('    options:{responsive:true,maintainAspectRatio:false,')
    h.append('    plugins:{legend:{display:false},tooltip:{callbacks:{label:function(c){return " "+c.raw+" кг";}}}},')
    h.append('    scales:{x:{grid:{display:false},ticks:{maxTicksLimit:5,font:{size:9},color:"#ccc"}},')
    h.append('            y:{grid:{color:"#f0ece6"},ticks:{font:{size:9},color:"#ccc"}}}}});')
    h.append('});')
    h.append('</script></body></html>')

    return ''.join(h)

def gen_report(tok, uid, name):
    pd, _ = gql(tok, 'getCurrentUser',
        'query getCurrentUser { getCurrentUser { id nickname firstName points dumbbells '
        'level { name } club { name } heroPass { availableCount endTime heroPass { name } } } }')
    u = pd.get('getCurrentUser') or {}
    nick = u.get('nickname') or u.get('firstName') or name
    lvl = (u.get('level') or {}).get('name','—')
    cl_ = (u.get('club') or {}).get('name','—')
    hp = u.get('heroPass') or {}
    hpl = hp.get('availableCount',0) or 0
    hpe = hp.get('endTime','')
    try: hpf = datetime.fromisoformat(hpe.replace('Z','+00:00')).strftime('%d.%m.%Y') if hpe else '—'
    except: hpf = '—'
    hp_name = (hp.get('heroPass') or {}).get('name') or 'Hero Pass'

    data = collect_all_data(tok, uid)
    a = analyse(data)

    rows = data['att_rows']
    fw = rows[0]['date'] if rows else '—'
    lw = rows[-1]['date'] if rows else '—'
    gd = datetime.now().strftime('%d.%m.%Y')

    return render_html(nick, lvl, cl_, hp_name, hpl, hpf, fw, lw, gd, a)

def handle(msg):
    cid = msg['chat']['id']
    text = msg.get('text','').strip()
    fn = msg.get('from',{}).get('first_name','Герой')
    st = states.get(cid,{})

    if text in ['/start','/help']:
        states[cid] = {'state':'idle'}
        w = '🏋️ <b>Hero\'s Journey Analytics</b>\n\n'
        w += 'Привет, ' + fn + '!\n\n'
        w += '📊 <b>Что будет в отчёте (этого нет в приложении):</b>\n'
        w += '• Персональный разбор — плато, дисбаланс, риски\n'
        w += '• Реальный тоннаж по месяцам и тренировкам\n'
        w += '• Тренды весов по каждому упражнению с датами\n'
        w += '• Детектор плато — вес не менялся 5+ сессий\n'
        w += '• Баланс Push/Pull/Legs — риск дисбаланса\n'
        w += '• ДНК отмен — когда и что ты срываешь\n'
        w += '• Ты vs Твой рекорд\n\n'
        w += '⏱ Сбор данных ~45 сек (запрашиваем каждую тренировку)\n\n'
        w += '📱 Введи номер из Hero\'s Journey:\n<i>Например: 87771234567</i>'
        tg('sendMessage', chat_id=cid, parse_mode='HTML', text=w,
           reply_markup={'keyboard':[[{'text':'📱 Поделиться номером','request_contact':True}]],
                         'resize_keyboard':True,'one_time_keyboard':True})
        return

    if msg.get('contact'):
        raw = msg['contact'].get('phone_number','')
        hj, disp = norm(raw)
        states[cid] = {'state':'waiting_code','phone':hj}
        ok = sms(hj)
        if ok:
            tg('sendMessage', chat_id=cid, parse_mode='HTML',
               text='📲 Код отправлен на <b>'+disp+'</b>\n\nВведи 4-значный код из SMS:',
               reply_markup={'remove_keyboard':True})
        else:
            tg('sendMessage', chat_id=cid, parse_mode='HTML',
               text='❌ Номер не найден в Hero\'s Journey.\nНапиши /start и попробуй снова.',
               reply_markup={'remove_keyboard':True})
            states[cid] = {'state':'idle'}
        return

    if st.get('state','idle') == 'idle':
        cl = text.replace('+','').replace(' ','').replace('-','')
        if cl.isdigit() and 10<=len(cl)<=12:
            hj, disp = norm(cl)
            states[cid] = {'state':'waiting_code','phone':hj}
            ok = sms(hj)
            if ok: send(cid,'📲 Код отправлен на <b>'+disp+'</b>\n\nВведи 4-значный код из SMS:')
            else: send(cid,'❌ Номер <b>'+disp+'</b> не найден. Проверь номер.'); states[cid]={'state':'idle'}
            return

    if st.get('state') == 'waiting_code':
        if text.isdigit() and len(text)==4:
            hj = st.get('phone','')
            send(cid, '⏳ <b>Собираю данные...</b>\n\n'
                 '🔄 Шаг 1/4: Загружаю историю записей\n'
                 '📊 Шаг 2/4: Запрашиваю тоннаж по месяцам\n'
                 '💪 Шаг 3/4: Собираю веса по тренировкам (~40-60 сек)\n'
                 '📈 Шаг 4/4: Строю аналитику\n\n'
                 'Пожалуйста, подожди...')
            tok = vcode(hj, text)
            if not tok:
                send(cid,'❌ Неверный код. Напиши /start.')
                states[cid] = {'state':'idle'}; return
            pd, _ = gql(tok,'getCurrentUser','query getCurrentUser { getCurrentUser { id nickname firstName } }')
            u = pd.get('getCurrentUser') or {}
            uid = u.get('id',''); fname = u.get('firstName') or u.get('nickname') or fn
            send(cid,'✅ Привет, <b>'+fname+'</b>!\n\n📊 Генерирую отчёт — это займёт ~45 секунд...')
            try:
                html = gen_report(tok, uid, fname)
                fs = fname.lower().replace(' ','_')
                cap = ('🎉 <b>Готово, '+fname+'!</b>\n\n'
                       'Открой HTML в браузере — там полный анализ:\n'
                       '• Тоннаж · Веса · Тренды\n'
                       '• Плато · Дисбаланс · ДНК отмен\n\n'
                       '/start — обновить отчёт')
                res = sdoc(cid, html.encode('utf-8'), 'hj_'+fs+'.html', cap)
                if res.get('error'): send(cid,'⚠️ '+str(res['error']))
            except Exception as e:
                send(cid,'⚠️ Ошибка: '+str(e)[:300]+'\n\nНапиши /start.')
            states[cid] = {'state':'idle'}
        else:
            send(cid,'Жду 4-значный код из SMS. /start — начать заново.')
        return

    send(cid,'Напиши /start',
         reply_markup={'keyboard':[[{'text':'📱 Поделиться номером','request_contact':True}]],
                       'resize_keyboard':True,'one_time_keyboard':True})


offset = 0
tg('setMyCommands', commands=[
    {'command':'start','description':'Получить Premium отчёт'},
    {'command':'help','description':'Помощь'}
])
try:
    u = requests.get(TG+'/getUpdates', params={'offset':-1,'timeout':1}, timeout=5).json()
    if u.get('result'): offset = u['result'][-1]['update_id']+1
except: pass

print('HJ Analytics Premium Bot v2 running!')
while True:
    try:
        u = requests.get(TG+'/getUpdates',
            params={'offset':offset,'timeout':25,'allowed_updates':['message']},
            timeout=35).json()
        if u.get('ok'):
            for upd in u.get('result',[]):
                offset = upd['update_id']+1
                msg = upd.get('message')
                if msg:
                    try: handle(msg)
                    except Exception as e:
                        c = msg.get('chat',{}).get('id')
                        if c: send(c,'⚠️ Ошибка: <code>'+type(e).__name__+': '+str(e)[:200]+'</code>')
    except: time.sleep(3)
