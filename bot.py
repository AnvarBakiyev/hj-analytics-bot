import os, requests, json, time
from collections import Counter, defaultdict
from datetime import datetime, timedelta

TOKEN = os.environ['BOT_TOKEN']
TG = 'https://api.telegram.org/bot' + TOKEN
HJ = 'https://admin.herosjourney.kz/graphql'
UA = 'HerosJourney/5.4.9 CFNetwork/3826.500.131 Darwin/24.5.0'
states = {}

TYPE_MUSCLE = {
    'push': 'Push', 'pull': 'Pull', 'legs': 'Legs', 'gluteLab': 'Glute',
    'fullBody': 'Full Body', 'upperBody': 'Upper Body', 'bootcamp': 'Bootcamp',
    'armBlast': 'Arms', 'metcon': 'Metcon', 'assessment': 'Assessment'
}
TYPE_LABELS = {
    'push': 'Push', 'pull': 'Pull', 'legs': 'Legs', 'gluteLab': 'Glute Lab',
    'fullBody': 'Full Body', 'upperBody': 'Upper Body', 'bootcamp': 'Bootcamp',
    'armBlast': 'Arm Blast', 'metcon': 'Metcon', 'assessment': 'Assessment'
}
WDO = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
WD_RU = {'Monday': 'Пн', 'Tuesday': 'Вт', 'Wednesday': 'Ср', 'Thursday': 'Чт',
          'Friday': 'Пт', 'Saturday': 'Сб', 'Sunday': 'Вс'}
WD_FULL = {'Monday': 'понедельник', 'Tuesday': 'вторник', 'Wednesday': 'среда',
           'Thursday': 'четверг', 'Friday': 'пятница', 'Saturday': 'суббота', 'Sunday': 'воскресенье'}
MUSCLE_GROUPS = ['Push', 'Pull', 'Legs', 'Glute', 'Full Body', 'Bootcamp', 'Arms']

def norm(raw):
    d = ''.join(c for c in raw if c.isdigit())
    if len(d) == 11 and d[0] == '8': hj, i = d, '7' + d[1:]
    elif len(d) == 11 and d[0] == '7': hj, i = '8' + d[1:], d
    elif len(d) == 10: hj, i = '8' + d, '7' + d
    else: hj = i = d
    disp = ('+7 (' + i[1:4] + ') ' + i[4:7] + '-' + i[7:9] + '-' + i[9:11]) if (len(i) == 11 and i[0] == '7') else '+' + i
    return hj, disp

def tg(m, **k):
    try: return requests.post(TG + '/' + m, json=k, timeout=15).json()
    except: return {}

def send(c, t, **k): return tg('sendMessage', chat_id=c, text=t, parse_mode='HTML', **k)

def sdoc(c, data, fn, cap=''):
    try:
        return requests.post(TG + '/sendDocument',
            data={'chat_id': c, 'caption': cap, 'parse_mode': 'HTML'},
            files={'document': (fn, data, 'text/html')}, timeout=60).json()
    except Exception as e: return {'error': str(e)}

def gql(tok, op, q, v=None):
    h = {'accept': '*/*', 'content-type': 'application/json',
         'authorization': 'Bearer ' + tok, 'user-agent': UA}
    try:
        r = requests.post(HJ, headers=h,
            json={'operationName': op, 'variables': v or {}, 'query': q}, timeout=30)
        d = r.json()
        return d.get('data', {}), d.get('errors', [])
    except Exception as e: return {}, [{'message': str(e)}]

def sms(p):
    h = {'accept': '*/*', 'content-type': 'application/json', 'user-agent': UA}
    q = 'mutation getVerificationCode($phoneNumber: String!) { getVerificationCode(phoneNumber: $phoneNumber) { status } }'
    try:
        r = requests.post(HJ, headers=h,
            json={'operationName': 'getVerificationCode', 'variables': {'phoneNumber': p}, 'query': q}, timeout=15)
        return (r.json().get('data') or {}).get('getVerificationCode', {}).get('status', '') == 'ok'
    except: return False

def vcode(p, c):
    h = {'accept': '*/*', 'content-type': 'application/json', 'user-agent': UA}
    q = 'mutation verifyPhoneNumberWithCode($input: CodeInput!) { verifyPhoneNumberWithCode(input: $input) { status token } }'
    try:
        r = requests.post(HJ, headers=h,
            json={'operationName': 'verifyPhoneNumberWithCode', 'variables': {'input': {'code': c, 'phoneNumber': p}}, 'query': q}, timeout=15)
        res = (r.json().get('data') or {}).get('verifyPhoneNumberWithCode', {})
        return res.get('token', '') if res.get('status') == '200' else None
    except: return None

def coach_letter(nick, n_att, n_months, ar, cr, push_cnt, pull_cnt,
                 plateaus, worst_cd, worst_cd_rate, eff_pct, bmo, prog_cnt, apw):
    p = []
    p.append('<p>' + nick + ', вот честный взгляд на твои <strong>' + str(n_att) + ' тренировок</strong> за ' + str(n_months) + ' месяцев.</p>')
    if ar >= 75:
        p.append('<p>🏆 <strong>Посещаемость ' + str(ar) + '%</strong> — топ-20% среди всех. Такая регулярность — фундамент любого прогресса. Это реально редкость.</p>')
    elif ar >= 55:
        p.append('<p>📊 <strong>Посещаемость ' + str(ar) + '%</strong> — хорошая база. Одна дополнительная тренировка в неделю даст ощутимый прирост силы и выносливости.</p>')
    else:
        p.append('<p>⚠️ <strong>Посещаемость ' + str(ar) + '%</strong> — главный барьер прямо сейчас. Тело адаптируется и растёт от регулярности, а не от разовых усилий.</p>')
    if push_cnt > 0 and pull_cnt > 0:
        ratio = push_cnt / pull_cnt
        if ratio > 1.4:
            p.append('<p>🔴 <strong>Push/Pull дисбаланс ' + str(round(ratio, 1)) + ':1</strong> — ' + str(push_cnt) + ' Push vs ' + str(pull_cnt) + ' Pull тренировок. Прямой риск импинджмент-синдрома плеча и нарушения осанки. Нужно выравнять до 1:1.</p>')
        elif ratio > 1.15:
            p.append('<p>🟡 <strong>Лёгкий Push/Pull перекос</strong>: ' + str(push_cnt) + ' vs ' + str(pull_cnt) + '. Добавь Pull-день — это предотвратит дисбаланс.</p>')
        else:
            p.append('<p>✅ <strong>Push/Pull баланс в норме</strong>: ' + str(push_cnt) + ' vs ' + str(pull_cnt) + '. Спина и грудь развиваются равномерно.</p>')
    if plateaus:
        names = ', '.join(pl['name'][:22] for pl in plateaus[:2])
        p.append('<p>🔴 <strong>Плато на ' + str(len(plateaus)) + ' упражнениях</strong>: ' + names + '. Вес не менялся 5+ сессий — тело адаптировалось. Нужен +2.5 кг на следующей тренировке, иначе прогресса нет.</p>')
    elif prog_cnt >= 3:
        p.append('<p>📈 <strong>' + str(prog_cnt) + ' упражнений в росте</strong> — прогрессивная перегрузка работает. Продолжай отслеживать веса и добавлять нагрузку.</p>')
    if worst_cd_rate > 50:
        day_n = WD_FULL.get(worst_cd, worst_cd).capitalize()
        p.append('<p>⚠️ <strong>' + day_n + ' — твой проблемный день</strong>: ' + str(worst_cd_rate) + '% записей отменяются. Либо не планируй тренировки в этот день, либо убирай всё лишнее.</p>')
    if eff_pct >= 40:
        p.append('<p>❤️ <strong>Хорошая интенсивность</strong>: ' + str(eff_pct) + '% тренировки в целевых зонах пульса 3–4. Именно здесь растёт сила и выносливость.</p>')
    elif eff_pct > 0:
        p.append('<p>🟡 <strong>Интенсивность можно поднять</strong>: лишь ' + str(eff_pct) + '% в целевых зонах 3–4. Попробуй сократить отдых между сетами.</p>')
    p.append('<p>📌 Рекорд активности: <strong>' + bmo[0] + ' — ' + str(bmo[1]) + ' тренировок</strong>. Это твоя планка — можешь побить?</p>')
    p.append('<p>➡️ <strong>Действие #1 прямо сейчас:</strong> ')
    if plateaus: p[-1] += '+2.5 кг на ' + plateaus[0]['name'][:25] + ' — сломай плато.</p>'
    elif push_cnt > pull_cnt * 1.3: p[-1] += 'Записаться на Pull прямо сейчас.</p>'
    elif ar < 60: p[-1] += '3 тренировки следующей недели без отмен. Просто три.</p>'
    else: p[-1] += 'Побить рекорд — ' + str(bmo[1]) + ' тренировок в месяц.</p>'
    return '\n'.join(p)

def build_css():
    c = []
    c.append('@import url(https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap);')
    c.append('*{box-sizing:border-box;margin:0;padding:0}')
    c.append('body{background:#f4f3ef;color:#1a1a1a;font-family:Inter,-apple-system,sans-serif;line-height:1.6}')
    c.append('.hero{background:linear-gradient(135deg,#0c1a0a 0%,#1a3318 45%,#2d5a27 100%);color:#fff;padding:52px 0 72px;position:relative;overflow:hidden}')
    c.append('.hero::before{content:"";position:absolute;top:-25%;right:-8%;width:480px;height:480px;background:radial-gradient(circle,rgba(168,217,160,.07),transparent 65%);border-radius:50%;pointer-events:none}')
    c.append('.hero::after{content:"";position:absolute;bottom:-15%;left:-5%;width:300px;height:300px;background:radial-gradient(circle,rgba(255,255,255,.03),transparent 65%);border-radius:50%;pointer-events:none}')
    c.append('.inner,.wrap{max-width:940px;margin:0 auto;padding:0 28px;position:relative}')
    c.append('.hero-badge{display:inline-flex;align-items:center;gap:6px;background:rgba(168,217,160,.14);border:1px solid rgba(168,217,160,.28);border-radius:100px;padding:5px 16px;font-size:12px;font-weight:600;margin-bottom:18px;color:#a8d9a0;letter-spacing:.2px}')
    c.append('.hero h1{font-size:38px;font-weight:900;line-height:1.13;margin-bottom:8px;letter-spacing:-0.6px}')
    c.append('.hero h1 .name{color:#a8d9a0}')
    c.append('.hero-sub{font-size:13px;color:rgba(255,255,255,.52);margin-bottom:28px}')
    c.append('.hs{display:flex;gap:32px;flex-wrap:wrap}')
    c.append('.hs-v{font-size:26px;font-weight:800;color:#a8d9a0;line-height:1}')
    c.append('.hs-l{font-size:10px;color:rgba(255,255,255,.48);margin-top:4px;text-transform:uppercase;letter-spacing:.6px}')
    c.append('.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:-42px;margin-bottom:0}')
    c.append('.kpi{background:#fff;border-radius:16px;box-shadow:0 8px 32px rgba(0,0,0,.10);border:1px solid #ede9e0;padding:20px 16px}')
    c.append('.ki{font-size:22px;margin-bottom:8px}')
    c.append('.kv{font-size:24px;font-weight:800;color:#1a1a1a;line-height:1;margin-bottom:2px}')
    c.append('.kl{font-size:11px;color:#888;text-transform:uppercase;letter-spacing:.5px;font-weight:600}')
    c.append('.ks{font-size:11px;color:#aaa;margin-top:3px}')
    c.append('.coach-wrap{background:#fff;border-radius:18px;box-shadow:0 4px 28px rgba(0,0,0,.06);border-left:5px solid #2d5a27;padding:30px 34px;margin-bottom:0}')
    c.append('.coach-lbl{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:2px;color:#2d5a27;margin-bottom:14px}')
    c.append('.coach-wrap p{font-size:14px;line-height:1.82;margin-bottom:10px;color:#2a2a2a}')
    c.append('.coach-wrap p:last-child{margin-bottom:0}')
    c.append('.sec{padding:30px 0 0}')
    c.append('.sl{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:2px;color:#2d5a27;margin-bottom:6px}')
    c.append('.st{font-size:23px;font-weight:800;letter-spacing:-.3px;margin-bottom:4px}')
    c.append('.ss{font-size:13px;color:#888;margin-bottom:22px}')
    c.append('.card{background:#fff;border-radius:14px;box-shadow:0 2px 18px rgba(0,0,0,.05);border:1px solid #ede9e0;padding:20px}')
    c.append('.g2{display:grid;grid-template-columns:1fr 1fr;gap:16px}')
    c.append('.g3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px}')
    c.append('.ct{font-size:13px;font-weight:700;color:#1a1a1a;margin-bottom:2px}')
    c.append('.cs{font-size:11px;color:#999;margin-bottom:14px}')
    c.append('.cw{position:relative}')
    c.append('.tgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}')
    c.append('.tc{background:#fff;border-radius:13px;box-shadow:0 2px 12px rgba(0,0,0,.05);border:1px solid #ede9e0;padding:14px}')
    c.append('.tn{font-size:12px;font-weight:700;margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}')
    c.append('.ts{display:flex;justify-content:space-between;font-size:11px;color:#999;margin-bottom:10px}')
    c.append('.tw{overflow-x:auto}')
    c.append('table{width:100%;border-collapse:collapse;font-size:12px}')
    c.append('th{text-align:left;padding:9px 12px;color:#888;font-weight:600;text-transform:uppercase;font-size:10px;letter-spacing:.5px;border-bottom:2px solid #ede9e0}')
    c.append('td{padding:10px 12px;border-bottom:1px solid #f0ece6}')
    c.append('tr:hover td{background:#fafaf7}')
    c.append('.hp-bar{background:#edf7f0;border:1px solid #c3e6cc;border-radius:12px;padding:14px 18px;display:flex;align-items:center;gap:14px}')
    c.append('.footer{margin-top:48px;padding:22px 0;border-top:1px solid #ede9e0;text-align:center;color:#aaa;font-size:11px}')
    c.append('@media(max-width:720px){.kpis,.g2,.g3,.tgrid{grid-template-columns:1fr 1fr}.hero h1{font-size:28px}.inner,.wrap{padding:0 16px}}')
    c.append('@media(max-width:480px){.kpis{grid-template-columns:1fr 1fr}.tgrid{grid-template-columns:1fr 1fr}}')
    return '\n'.join(c)

def gen_report(tok, uid, name):
    pd, _ = gql(tok, 'getCurrentUser',
        'query getCurrentUser { getCurrentUser { id nickname firstName points dumbbells level { name } club { name } heroPass { availableCount endTime heroPass { name } } } }')
    u = pd.get('getCurrentUser') or {}

    bd, _ = gql(tok, 'userBookings',
        'query userBookings($userId: ID) { userBookings(userId: $userId) { id status event { id startTime programSet { name type } trainer { nickname } club { name } } } }',
        {'userId': uid})
    ab = bd.get('userBookings') or []
    att_raw = [b for b in ab if b.get('status') == 'attended']
    can_raw = [b for b in ab if b.get('status') == 'canceled']

    def parse_b(b, keep_eid=False):
        ev = b.get('event') or {}; ps = ev.get('programSet') or {}
        tr = ev.get('trainer') or {}; cl = ev.get('club') or {}
        s = ev.get('startTime', '')
        try:
            dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
            row = {'date': dt.strftime('%Y-%m-%d'), 'month': dt.strftime('%Y-%m'),
                   'wd': dt.strftime('%A'), 'h': dt.hour,
                   'prog': ps.get('name', ''), 'type': ps.get('type', ''),
                   'tr': tr.get('nickname', ''), 'cl': cl.get('name', '')}
            if keep_eid: row['eid'] = ev.get('id', '')
            return row
        except: return None

    rows = [r for r in (parse_b(b, True) for b in att_raw) if r]
    can_rows = [r for r in (parse_b(b) for b in can_raw) if r]
    rows.sort(key=lambda x: x['date'])

    wh_data, _ = gql(tok, 'userWeightsHistory',
        'query userWeightsHistory { userWeightsHistory { maxWeight exercise { id name } weights { weight event { startTime } } } }')
    weight_history = wh_data.get('userWeightsHistory') or []

    q_hr = ('query summaryHeartRates($user: ID!, $event: ID!) { summaryHeartRates(user: $user, event: $event) { '
            'max_hr average_hr calories zone_duration { Zone0 Zone1 Zone2 Zone3 Zone4 Zone5 } } }')
    hr_cache = {}
    for row in rows[-20:]:
        eid = row.get('eid', '')
        if eid:
            hd, _ = gql(tok, 'summaryHeartRates', q_hr, {'user': uid, 'event': eid})
            shr = hd.get('summaryHeartRates')
            if shr: hr_cache[eid] = shr
            time.sleep(0.08)

    total = len(ab); n_att = len(rows); n_can = len(can_rows)
    ar = round(n_att / total * 100, 1) if total else 0
    cr = round(n_can / total * 100, 1) if total else 0
    bm = Counter(r['month'] for r in rows if r['month'])
    bt = Counter(r['type'] for r in rows if r['type'])
    btr = Counter(r['tr'] for r in rows if r['tr'])
    bwd = Counter(r['wd'] for r in rows)
    bh = Counter(r['h'] for r in rows)
    ms = sorted(bm.items())
    wd_vals = [bwd.get(d, 0) for d in WDO]
    bmo = max(bm.items(), key=lambda x: x[1]) if bm else ('—', 0)
    tt = btr.most_common(1)[0] if btr else ('—', 0)
    ph = max(bh.items(), key=lambda x: x[1])[0] if bh else 8
    apw = round(n_att / max(len(ms) * 4.3, 1), 1)

    cutoff = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
    mc_all = Counter(TYPE_MUSCLE.get(r['type'], 'Other') for r in rows)
    mc_90 = Counter(TYPE_MUSCLE.get(r['type'], 'Other') for r in rows if r['date'] >= cutoff)
    muscle_vals = [mc_90.get(mg, 0) for mg in MUSCLE_GROUPS]
    push_cnt = mc_all.get('Push', 0); pull_cnt = mc_all.get('Pull', 0)

    plateaus = []; progressing = []; ex_trends = []
    for item in weight_history:
        ex = item.get('exercise') or {}
        ex_name = ex.get('name', '')
        if not ex_name: continue
        wl = item.get('weights') or []; max_w = item.get('maxWeight', 0) or 0
        dated = []
        for w in wl:
            ev_d = w.get('event') or {}; s = ev_d.get('startTime', ''); wt = w.get('weight', 0) or 0
            if s and wt > 0:
                try:
                    dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
                    dated.append({'date': dt.strftime('%Y-%m-%d'), 'w': wt})
                except: pass
        if not dated: continue
        dated.sort(key=lambda x: x['date'])
        if len(dated) >= 4:
            ex_trends.append({'name': ex_name,
                'dates': [d['date'][5:] for d in dated],
                'weights': [d['w'] for d in dated],
                'max': max_w, 'sessions': len(dated),
                'first': dated[0]['w'], 'last': dated[-1]['w'],
                'prog': round(dated[-1]['w'] - dated[0]['w'], 1)})
        if len(dated) >= 5:
            last5 = [d['w'] for d in dated[-5:]]
            if max(last5) - min(last5) < 2.5:
                plateaus.append({'name': ex_name, 'weight': last5[-1], 'sessions': len(dated)})
            elif dated[-1]['w'] > dated[0]['w']:
                progressing.append({'name': ex_name, 'gain': round(dated[-1]['w'] - dated[0]['w'], 1)})
    ex_trends.sort(key=lambda x: -x['sessions'])
    top_trends = ex_trends[:6]

    can_wd = Counter(r['wd'] for r in can_rows if r.get('wd'))
    att_wd = Counter(r['wd'] for r in rows if r.get('wd'))
    can_rate_wd = {}
    for day in WDO:
        tot = att_wd.get(day, 0) + can_wd.get(day, 0)
        can_rate_wd[day] = round(can_wd.get(day, 0) / tot * 100) if tot > 0 else 0
    can_wd_vals = [can_rate_wd.get(d, 0) for d in WDO]
    worst_cd = max(can_rate_wd.items(), key=lambda x: x[1]) if can_rate_wd else ('Monday', 0)
    can_type = Counter(r['type'] for r in can_rows if r.get('type'))
    att_type = Counter(r['type'] for r in rows if r.get('type'))
    can_rate_type = {}
    for t in set(list(att_type) + list(can_type)):
        tot = att_type.get(t, 0) + can_type.get(t, 0)
        can_rate_type[t] = round(can_type.get(t, 0) / tot * 100) if tot > 0 else 0
    can_type_sorted = sorted([(TYPE_LABELS.get(t, t), r) for t, r in can_rate_type.items() if r > 0], key=lambda x: -x[1])[:6]

    zone_sums = [0.0] * 6; zone_cnt = 0; cal_list = []
    for eid, shr in hr_cache.items():
        zd = shr.get('zone_duration') or {}
        if any(zd.get('Zone' + str(i), 0) for i in range(6)):
            for i in range(6): zone_sums[i] += zd.get('Zone' + str(i), 0) or 0
            zone_cnt += 1
        cal = shr.get('calories', 0) or 0
        if cal > 0: cal_list.append(cal)
    avg_zones = [round(z / zone_cnt / 60, 1) if zone_cnt > 0 else 0 for z in zone_sums]
    avg_cal = round(sum(cal_list) / len(cal_list)) if cal_list else 0
    total_z = sum(avg_zones)
    eff_pct = round((avg_zones[3] + avg_zones[4]) / total_z * 100) if total_z > 0 else 0

    nick = u.get('nickname') or u.get('firstName') or name
    lvl = (u.get('level') or {}).get('name', '—')
    cl_ = (u.get('club') or {}).get('name', '—')
    hp = u.get('heroPass') or {}; hpl = hp.get('availableCount', 0) or 0
    hpe = hp.get('endTime', '')
    try: hpf = datetime.fromisoformat(hpe.replace('Z', '+00:00')).strftime('%d.%m.%Y') if hpe else '—'
    except: hpf = '—'
    hp_name = (hp.get('heroPass') or {}).get('name') or 'Hero Pass'
    fw = rows[0]['date'] if rows else '—'; lw = rows[-1]['date'] if rows else '—'
    gd = datetime.now().strftime('%d.%m.%Y')
    gr = 'A' if ar >= 80 else 'B+' if ar >= 65 else 'B' if ar >= 55 else 'C+'

    cl_html = coach_letter(nick, n_att, len(ms), ar, cr, push_cnt, pull_cnt,
                           plateaus, worst_cd[0], worst_cd[1], eff_pct, bmo, len(progressing), apw)

    def jd(x): return json.dumps(x, ensure_ascii=False)

    tbars = ''
    if btr:
        mx = btr.most_common(1)[0][1]
        for t, c in btr.most_common(6):
            p = round(c / mx * 100)
            tbars += ('<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">'
                      '<div style="font-size:13px;font-weight:600;width:110px;overflow:hidden;white-space:nowrap">' + t + '</div>'
                      '<div style="flex:1;height:6px;background:#e8e4dd;border-radius:3px;overflow:hidden">'
                      '<div style="height:100%;width:' + str(p) + '%;background:linear-gradient(90deg,#2d5a27,#a8d9a0);border-radius:3px"></div></div>'
                      '<div style="font-size:13px;font-weight:700;color:#2d5a27;width:28px;text-align:right">' + str(c) + '</div>'
                      '</div>')

    plateau_html = ''
    for pl in plateaus[:5]:
        plateau_html += ('<div style="display:flex;align-items:center;gap:12px;padding:10px 14px;'
                         'background:#fdf2f1;border:1px solid #f5c6c3;border-radius:10px;margin-bottom:8px">'
                         '<div style="font-size:18px">🔴</div>'
                         '<div style="flex:1"><div style="font-size:13px;font-weight:600">' + pl['name'] + '</div>'
                         '<div style="font-size:11px;color:#6b6b6b">' + str(pl['weight']) + ' кг · ' + str(pl['sessions']) + ' сессий без изменений</div></div>'
                         '<div style="font-size:11px;font-weight:700;color:#c0392b;padding:3px 8px;'
                         'background:#fff0ee;border:1px solid #f5c6c3;border-radius:6px">ПЛАТО</div></div>')
    if not plateaus:
        plateau_html = ('<div style="text-align:center;padding:22px;color:#2d7d46;font-size:14px;font-weight:600">'
                        '✅ Плато не обнаружено — ты прогрессируешь!</div>')
    for pg in sorted(progressing, key=lambda x: -x['gain'])[:4]:
        plateau_html += ('<div style="display:flex;align-items:center;gap:12px;padding:10px 14px;'
                         'background:#edf7f0;border:1px solid #c3e6cc;border-radius:10px;margin-bottom:8px">'
                         '<div style="font-size:18px">📈</div>'
                         '<div style="flex:1"><div style="font-size:13px;font-weight:600">' + pg['name'] + '</div>'
                         '<div style="font-size:11px;color:#6b6b6b">рост +' + str(pg['gain']) + ' кг за все сессии</div></div>'
                         '<div style="font-size:11px;font-weight:700;color:#2d7d46;padding:3px 8px;'
                         'background:#e8f5ea;border:1px solid #c3e6cc;border-radius:6px">РОСТ ↑</div></div>')

    trend_cards = ''
    TREND_COLORS = ['#f5a623', '#4ade80', '#60a5fa', '#c084fc', '#f87171', '#fbbf24']
    for i, ex in enumerate(top_trends):
        prog_color = '#2d7d46' if ex['prog'] > 0 else ('#c0392b' if ex['prog'] < 0 else '#888')
        prog_str = ('+' if ex['prog'] > 0 else '') + str(ex['prog']) + ' кг'
        trend_cards += ('<div class="tc">'
                        '<div class="tn">' + ex['name'] + '</div>'
                        '<div class="ts"><span>' + str(ex['sessions']) + ' сессий</span>'
                        '<span style="font-weight:700;color:' + prog_color + '">' + prog_str + '</span></div>'
                        '<div class="cw" style="height:90px"><canvas id="tr' + str(i) + '"></canvas></div>'
                        '<div style="display:flex;justify-content:space-between;font-size:10px;color:#999;margin-top:6px">'
                        '<span>старт: ' + str(ex['first']) + ' кг</span>'
                        '<span>макс: ' + str(ex['max']) + ' кг</span></div></div>')

    now_m = datetime.now().strftime('%Y-%m')
    prev_m_str = (datetime.now().replace(day=1) - timedelta(days=1)).strftime('%Y-%m')
    cur_mc = bm.get(now_m, 0); prev_mc = bm.get(prev_m_str, 0)
    yvby = ''
    comps = [
        ('Тренировок в этом месяце', str(cur_mc), str(bmo[1]) + ' (рекорд)', cur_mc >= bmo[1] * 0.75),
        ('Тренировок в прошлом месяце', str(prev_mc), str(bmo[1]) + ' (рекорд)', prev_mc >= bmo[1] * 0.75),
        ('Тренировок в неделю', str(apw), '3.0+', apw >= 3.0),
        ('Посещаемость', str(ar) + '%', '80%', ar >= 75),
    ]
    for label, cur, best, good in comps:
        col = '#2d7d46' if good else '#c0392b'; ico = '✅' if good else '❌'
        yvby += ('<div style="display:flex;align-items:center;justify-content:space-between;'
                 'padding:12px 16px;background:#f8f7f3;border-radius:10px;margin-bottom:8px">'
                 '<div style="font-size:13px;color:#6b6b6b">' + label + '</div>'
                 '<div style="display:flex;align-items:center;gap:18px">'
                 '<div style="text-align:center"><div style="font-size:19px;font-weight:800;color:' + col + '">' + cur + '</div>'
                 '<div style="font-size:10px;color:#aaa">сейчас</div></div>'
                 '<div style="font-size:20px">' + ico + '</div>'
                 '<div style="text-align:center"><div style="font-size:19px;font-weight:800;color:#2d5a27">' + best + '</div>'
                 '<div style="font-size:10px;color:#aaa">цель</div></div>'
                 '</div></div>')

    tr_html = ''
    for r in reversed(rows[-50:]):
        tr_html += ('<tr><td style="white-space:nowrap">' + r['date'] + '</td>'
                    '<td>' + r['prog'] + '</td><td>' + r['tr'] + '</td>'
                    '<td style="color:#6b6b6b">' + r['cl'] + '</td></tr>')

    h = []
    h.append('<!DOCTYPE html><html lang="ru"><head>')
    h.append('<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">')
    h.append('<title>' + nick + ' · HJ Premium Report</title>')
    h.append('<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>')
    h.append('<style>' + build_css() + '</style>')
    h.append('</head><body>')

    h.append('<div class="hero"><div class="inner">')
    h.append('<div class="hero-badge">⚔️ Hero\'s Journey · Premium Анализ</div>')
    h.append('<h1>Твои тренировки,<br><span class="name">' + nick + '</span></h1>')
    h.append('<p class="hero-sub">' + lvl + ' · ' + cl_ + ' · ' + fw + ' — ' + lw + '</p>')
    h.append('<div class="hs">')
    h.append('<div><div class="hs-v">' + str(n_att) + '</div><div class="hs-l">тренировок</div></div>')
    h.append('<div><div class="hs-v">' + str(len(ms)) + '</div><div class="hs-l">месяцев</div></div>')
    h.append('<div><div class="hs-v">' + str(ar) + '%</div><div class="hs-l">посещаемость</div></div>')
    h.append('<div><div class="hs-v">' + gr + '</div><div class="hs-l">оценка</div></div>')
    h.append('<div><div class="hs-v">' + str(hpl) + '</div><div class="hs-l">визитов осталось</div></div>')
    h.append('</div></div></div>')

    h.append('<div class="wrap">')

    h.append('<div class="kpis">')
    h.append('<div class="kpi"><div class="ki">📅</div><div class="kv">' + str(apw) + '</div><div class="kl">Тренировок/нед.</div></div>')
    h.append('<div class="kpi"><div class="ki">🏆</div><div class="kv">' + str(bmo[1]) + '</div><div class="kl">Лучший месяц</div><div class="ks">' + bmo[0] + '</div></div>')
    h.append('<div class="kpi"><div class="ki">❌</div><div class="kv">' + str(cr) + '%</div><div class="kl">Отмен</div><div class="ks">' + str(n_can) + ' из ' + str(total) + '</div></div>')
    h.append('<div class="kpi"><div class="ki">🤝</div><div class="kv">' + str(tt[1]) + '</div><div class="kl">' + tt[0] + '</div><div class="ks">топ тренер</div></div>')
    h.append('</div>')

    h.append('<div class="sec"><div class="sl">Персональный разбор</div><div class="st">Анализ от фитнес-аналитика</div>')
    h.append('<div class="coach-wrap"><div class="coach-lbl">💬 Только то, чего нет в приложении</div>')
    h.append(cl_html)
    h.append('</div></div>')

    h.append('<div style="padding-top:22px">')
    h.append('<div class="hp-bar"><div style="font-size:24px">🎫</div><div>')
    h.append('<div style="font-size:14px;font-weight:700">' + hp_name + '</div>')
    h.append('<div style="font-size:12px;color:#6b6b6b">Визитов: <b style="color:#2d5a27">' + str(hpl) + '</b> · До: <b>' + hpf + '</b></div>')
    h.append('</div></div></div>')

    h.append('<div class="sec"><div class="sl">01 — Активность</div><div class="st">Динамика и баланс нагрузок</div><div class="ss">Тренировки по месяцам · Баланс мышечных групп за последние 90 дней</div>')
    h.append('<div class="g2">')
    h.append('<div class="card"><div class="ct">Тренировок по месяцам</div><div class="cs">Общий объём посещений</div><div class="cw" style="height:220px"><canvas id="cMonth"></canvas></div></div>')
    h.append('<div class="card"><div class="ct">Баланс мышечных групп (90 дней)</div><div class="cs">Равномерность нагрузок — радар должен быть округлым</div><div class="cw" style="height:220px"><canvas id="cRadar"></canvas></div></div>')
    h.append('</div></div>')

    h.append('<div class="sec"><div class="sl">02 — Структура</div><div class="st">Типы · Дни недели · Тренеры</div><div class="ss">Из чего состоит твоя программа</div>')
    h.append('<div class="g3">')
    h.append('<div class="card"><div class="ct">Типы тренировок</div><div class="cs">Доли программ</div><div class="cw" style="height:200px"><canvas id="cType"></canvas></div></div>')
    h.append('<div class="card"><div class="ct">По дням недели</div><div class="cs">Когда ты тренируешься чаще</div><div class="cw" style="height:200px"><canvas id="cWd"></canvas></div></div>')
    h.append('<div class="card"><div class="ct">Топ тренеров</div><div class="cs">Совместных занятий</div><div style="padding-top:6px">' + tbars + '</div></div>')
    h.append('</div></div>')

    h.append('<div class="sec"><div class="sl">03 — Детектор плато</div><div class="st">Прогресс по упражнениям</div><div class="ss">🔴 Вес не менялся 5+ сессий · 📈 Реальный рост зафиксирован</div>')
    h.append('<div class="card">' + plateau_html + '</div></div>')

    if top_trends:
        h.append('<div class="sec"><div class="sl">04 — Динамика весов</div><div class="st">Тренды по ключевым упражнениям</div><div class="ss">История весов от первой до последней сессии · Видно плато, спады, рекорды</div>')
        h.append('<div class="tgrid">' + trend_cards + '</div></div>')

    h.append('<div class="sec"><div class="sl">05 — ДНК отмен</div><div class="st">Когда и что ты отменяешь</div><div class="ss">Твой персональный профиль отмен — то, чего ты сам не замечаешь</div>')
    h.append('<div class="g2">')
    h.append('<div class="card"><div class="ct">% отмен по дням недели</div><div class="cs">Красный — твой проблемный день</div><div class="cw" style="height:195px"><canvas id="cCanWd"></canvas></div></div>')
    h.append('<div class="card"><div class="ct">% отмен по типу тренировки</div><div class="cs">Что чаще всего срывается</div><div class="cw" style="height:195px"><canvas id="cCanType"></canvas></div></div>')
    h.append('</div></div>')

    if zone_cnt > 0:
        eff_col = '#2d7d46' if eff_pct >= 40 else '#c0392b'
        h.append('<div class="sec"><div class="sl">06 — Пульсовые зоны</div><div class="st">Интенсивность тренировок</div><div class="ss">Среднее по ' + str(zone_cnt) + ' тренировкам · Зоны 3–4 — целевые для силы и выносливости</div>')
        h.append('<div class="g2">')
        h.append('<div class="card"><div class="ct">Зоны пульса (мин. среднее)</div><div class="cs">Идеал: максимум времени в зонах 3–4</div><div class="cw" style="height:205px"><canvas id="cZones"></canvas></div></div>')
        h.append('<div class="card" style="display:flex;flex-direction:column;align-items:center;justify-content:center;gap:24px">')
        h.append('<div style="text-align:center"><div style="font-size:58px;font-weight:900;color:' + eff_col + '">' + str(eff_pct) + '%</div><div style="font-size:13px;color:#888;margin-top:4px">времени в целевых зонах 3–4</div></div>')
        h.append('<div style="text-align:center"><div style="font-size:40px;font-weight:800;color:#1e4d8c">' + str(avg_cal) + '</div><div style="font-size:13px;color:#888;margin-top:4px">ккал в среднем за тренировку</div></div>')
        h.append('</div></div></div>')

    sn = '07' if zone_cnt > 0 else '06'
    h.append('<div class="sec"><div class="sl">' + sn + ' — Ты vs Лучший ты</div><div class="st">Текущий уровень vs Твой рекорд</div><div class="ss">Насколько ты близко к своим лучшим показателям</div>')
    h.append('<div class="card">' + yvby + '</div></div>')

    sn2 = '08' if zone_cnt > 0 else '07'
    h.append('<div class="sec"><div class="sl">' + sn2 + ' — История</div><div class="st">Последние 50 тренировок</div>')
    h.append('<div class="card"><div class="tw"><table><thead><tr>'
             '<th>Дата</th><th>Программа</th><th>Тренер</th><th>Клуб</th>'
             '</tr></thead><tbody>' + tr_html + '</tbody></table></div></div></div>')

    h.append('</div>')
    h.append('<div class="footer"><div class="wrap">Отчёт ' + gd + ' · HJ Analytics Premium · ' + str(n_att) + ' тренировок<br>Аналитика недоступна в приложении Hero\'s Journey</div></div>')

    h.append('<script>')
    h.append('Chart.defaults.font.family = "Inter,sans-serif";')
    h.append('Chart.defaults.color = "#888";')

    mv = [m[1] for m in ms]
    h.append('var mv = ' + jd(mv) + ';')
    h.append('new Chart(document.getElementById("cMonth"),{type:"bar",data:{labels:' + jd([m[0] for m in ms]) + ',datasets:[{data:mv,backgroundColor:mv.map(function(v){return v===Math.max.apply(null,mv)?"#2d5a27":"#a8d9a0";}),borderRadius:8,borderSkipped:false}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{display:false},ticks:{maxRotation:45,font:{size:10}}},y:{grid:{color:"#e8e4dd"}}}}});')

    h.append('new Chart(document.getElementById("cRadar"),{type:"radar",data:{labels:' + jd(MUSCLE_GROUPS) + ',datasets:[{data:' + jd(muscle_vals) + ',backgroundColor:"rgba(45,90,39,0.14)",borderColor:"#2d5a27",borderWidth:2.5,pointBackgroundColor:"#2d5a27",pointRadius:4}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{r:{grid:{color:"#e8e4dd"},ticks:{display:false},pointLabels:{font:{size:10}}}}}});')

    type_top7 = bt.most_common(7)
    h.append('new Chart(document.getElementById("cType"),{type:"doughnut",data:{labels:' + jd([TYPE_LABELS.get(k, k) for k, _ in type_top7]) + ',datasets:[{data:' + jd([v for _, v in type_top7]) + ',backgroundColor:["#2d5a27","#a8d9a0","#c8512a","#f5a623","#1e4d8c","#60a5fa","#c084fc"],borderWidth:3,borderColor:"#fff"}]},options:{responsive:true,maintainAspectRatio:false,cutout:"55%",plugins:{legend:{position:"right",labels:{font:{size:10},boxWidth:10}}}}});')

    h.append('var wv = ' + jd(wd_vals) + ';')
    h.append('new Chart(document.getElementById("cWd"),{type:"bar",data:{labels:' + jd([WD_RU.get(d, d) for d in WDO]) + ',datasets:[{data:wv,backgroundColor:wv.map(function(v){return v===Math.max.apply(null,wv)?"#2d5a27":"#d4e8d1";}),borderRadius:6,borderSkipped:false}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{display:false}},y:{grid:{color:"#e8e4dd"}}}}});')

    h.append('var cwv = ' + jd(can_wd_vals) + ';')
    h.append('new Chart(document.getElementById("cCanWd"),{type:"bar",data:{labels:' + jd([WD_RU.get(d, d) for d in WDO]) + ',datasets:[{data:cwv,backgroundColor:cwv.map(function(v){return v===Math.max.apply(null,cwv)?"#c0392b":"#f5c6c3";}),borderRadius:6,borderSkipped:false}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:function(c){return c.raw+"%";}}}},scales:{x:{grid:{display:false}},y:{grid:{color:"#e8e4dd"},ticks:{callback:function(v){return v+"%";}}}}}});')

    h.append('new Chart(document.getElementById("cCanType"),{type:"bar",data:{labels:' + jd([x[0] for x in can_type_sorted]) + ',datasets:[{data:' + jd([x[1] for x in can_type_sorted]) + ',backgroundColor:"#f87171",borderRadius:6,borderSkipped:false}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:function(c){return c.raw+"%";}}}},scales:{x:{grid:{display:false},ticks:{maxRotation:30,font:{size:10}}},y:{grid:{color:"#e8e4dd"},ticks:{callback:function(v){return v+"%";}}}}}});')

    if zone_cnt > 0:
        h.append('new Chart(document.getElementById("cZones"),{type:"bar",data:{labels:["Зона 0","Зона 1","Зона 2","Зона 3","Зона 4","Зона 5"],datasets:[{data:' + jd(avg_zones) + ',backgroundColor:["#93c5fd","#6ee7b7","#a3e635","#f5a623","#f87171","#ef4444"],borderRadius:6,borderSkipped:false}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{display:false}},y:{grid:{color:"#e8e4dd"},title:{display:true,text:"мин.",color:"#888"}}}}});')

    h.append('var TRENDS = ' + jd(top_trends) + ';')
    h.append('var TC = ["#f5a623","#4ade80","#60a5fa","#c084fc","#f87171","#fbbf24"];')
    h.append('TRENDS.forEach(function(ex,i){')
    h.append('  var cv = document.getElementById("tr"+i); if(!cv) return;')
    h.append('  var grd = cv.getContext("2d").createLinearGradient(0,0,0,90);')
    h.append('  grd.addColorStop(0,TC[i]+"30"); grd.addColorStop(1,TC[i]+"00");')
    h.append('  new Chart(cv,{type:"line",data:{labels:ex.dates,datasets:[{data:ex.weights,')
    h.append('    borderColor:TC[i],backgroundColor:grd,borderWidth:2.5,')
    h.append('    pointRadius:ex.dates.length>14?1:3,pointHoverRadius:5,fill:true,tension:0.35}]},')
    h.append('    options:{responsive:true,maintainAspectRatio:false,')
    h.append('    plugins:{legend:{display:false},tooltip:{callbacks:{label:function(c){return " "+c.raw+" кг";}}}},')
    h.append('    scales:{x:{grid:{display:false},ticks:{maxTicksLimit:5,font:{size:9},color:"#bbb"}},')
    h.append('            y:{grid:{color:"#ede9e0"},ticks:{font:{size:9},color:"#bbb"}}}}});')
    h.append('});')
    h.append('</script>')
    h.append('</body></html>')

    return ''.join(h)

def handle(msg):
    cid = msg['chat']['id']
    text = msg.get('text', '').strip()
    fn = msg.get('from', {}).get('first_name', 'Герой')
    st = states.get(cid, {})

    if text in ['/start', '/help']:
        states[cid] = {'state': 'idle'}
        w = '🏋️ <b>Hero\'s Journey Analytics</b>\n\n'
        w += 'Привет, ' + fn + '!\n\n'
        w += '📊 <b>Premium отчёт — то, чего нет в приложении:</b>\n'
        w += '• Персональный разбор от фитнес-аналитика\n'
        w += '• Детектор плато по каждому упражнению\n'
        w += '• Динамика весов с графиками трендов\n'
        w += '• Баланс мышечных групп Push/Pull/Legs\n'
        w += '• ДНК отмен — когда и что ты срываешь\n'
        w += '• Анализ пульсовых зон и калорий\n'
        w += '• Ты vs Твой лучший результат\n\n'
        w += '📱 Введи номер телефона из Hero\'s Journey:\n'
        w += '<i>Например: 87771234567</i>'
        tg('sendMessage', chat_id=cid, parse_mode='HTML', text=w,
           reply_markup={'keyboard': [[{'text': '📱 Поделиться номером', 'request_contact': True}]],
                         'resize_keyboard': True, 'one_time_keyboard': True})
        return

    if msg.get('contact'):
        raw = msg['contact'].get('phone_number', '')
        hj, disp = norm(raw)
        states[cid] = {'state': 'waiting_code', 'phone': hj}
        ok = sms(hj)
        if ok:
            tg('sendMessage', chat_id=cid, parse_mode='HTML',
               text='📲 Код отправлен на <b>' + disp + '</b>\n\nВведи 4-значный код из SMS:',
               reply_markup={'remove_keyboard': True})
        else:
            tg('sendMessage', chat_id=cid, parse_mode='HTML',
               text='❌ Номер не найден в Hero\'s Journey.\nНапиши /start и попробуй снова.',
               reply_markup={'remove_keyboard': True})
            states[cid] = {'state': 'idle'}
        return

    if st.get('state', 'idle') == 'idle':
        cl = text.replace('+', '').replace(' ', '').replace('-', '')
        if cl.isdigit() and 10 <= len(cl) <= 12:
            hj, disp = norm(cl)
            states[cid] = {'state': 'waiting_code', 'phone': hj}
            ok = sms(hj)
            if ok:
                send(cid, '📲 Код отправлен на <b>' + disp + '</b>\n\nВведи 4-значный код из SMS:')
            else:
                send(cid, '❌ Номер <b>' + disp + '</b> не найден в HJ. Проверь номер.')
                states[cid] = {'state': 'idle'}
            return

    if st.get('state') == 'waiting_code':
        if text.isdigit() and len(text) == 4:
            hj = st.get('phone', '')
            send(cid, '⏳ Авторизуюсь и собираю данные...\n🔬 Анализирую веса, пульс и паттерны (~45 сек)')
            tok = vcode(hj, text)
            if not tok:
                send(cid, '❌ Неверный код. Напиши /start.')
                states[cid] = {'state': 'idle'}
                return
            pd, _ = gql(tok, 'getCurrentUser', 'query getCurrentUser { getCurrentUser { id nickname firstName } }')
            u = pd.get('getCurrentUser') or {}
            uid = u.get('id', ''); fname = u.get('firstName') or u.get('nickname') or fn
            send(cid, '✅ Привет, <b>' + fname + '</b>!\n\n📊 Генерирую Premium отчёт...')
            try:
                html = gen_report(tok, uid, fname)
                fs = fname.lower().replace(' ', '_')
                res = sdoc(cid, html.encode('utf-8'), 'hj_premium_' + fs + '.html',
                    '🎉 <b>Premium отчёт готов, ' + fname + '!</b>\n\n'
                    '📊 Открой в браузере:\n'
                    '• Графики трендов весов\n'
                    '• Детектор плато\n'
                    '• Баланс мышц · ДНК отмен\n'
                    '• Персональный разбор\n\n'
                    '/start — обновить в любое время.')
                if res.get('error'): send(cid, '⚠️ ' + str(res['error']))
            except Exception as e:
                send(cid, '⚠️ Ошибка: ' + str(e)[:200] + '\n\nНапиши /start.')
            states[cid] = {'state': 'idle'}
        else:
            send(cid, 'Жду 4-значный код из SMS. /start — начать заново.')
        return

    send(cid, 'Напиши /start',
         reply_markup={'keyboard': [[{'text': '📱 Поделиться номером', 'request_contact': True}]],
                       'resize_keyboard': True, 'one_time_keyboard': True})

offset = 0
tg('setMyCommands', commands=[
    {'command': 'start', 'description': 'Получить Premium отчёт'},
    {'command': 'help', 'description': 'Помощь'}
])
try:
    u = requests.get(TG + '/getUpdates', params={'offset': -1, 'timeout': 1}, timeout=5).json()
    if u.get('result'): offset = u['result'][-1]['update_id'] + 1
except: pass

print('HJ Analytics Premium Bot running!')
while True:
    try:
        u = requests.get(TG + '/getUpdates',
            params={'offset': offset, 'timeout': 25, 'allowed_updates': ['message']},
            timeout=35).json()
        if u.get('ok'):
            for upd in u.get('result', []):
                offset = upd['update_id'] + 1
                msg = upd.get('message')
                if msg:
                    try: handle(msg)
                    except Exception as e:
                        c = msg.get('chat', {}).get('id')
                        if c: send(c, '⚠️ Ошибка. Напиши /start.')
    except: time.sleep(3)
