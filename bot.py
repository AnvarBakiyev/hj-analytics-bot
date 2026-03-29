import os
import requests
import json
import time
from collections import Counter
from datetime import datetime

TOKEN = os.environ['BOT_TOKEN']
TG = 'https://api.telegram.org/bot' + TOKEN
HJ = 'https://admin.herosjourney.kz/graphql'
UA = 'HerosJourney/5.4.9 CFNetwork/3826.500.131 Darwin/24.5.0'
states = {}

def norm(raw):
    d = ''.join(c for c in raw if c.isdigit())
    if len(d) == 11 and d[0] == '8':
        hj, i = d, '7' + d[1:]
    elif len(d) == 11 and d[0] == '7':
        hj, i = '8' + d[1:], d
    elif len(d) == 10:
        hj, i = '8' + d, '7' + d
    else:
        hj = i = d
    if len(i) == 11 and i[0] == '7':
        disp = '+7 (' + i[1:4] + ') ' + i[4:7] + '-' + i[7:9] + '-' + i[9:11]
    else:
        disp = '+' + i
    return hj, disp

def tg(m, **k):
    try:
        return requests.post(TG + '/' + m, json=k, timeout=15).json()
    except:
        return {}

def send(c, t, **k):
    return tg('sendMessage', chat_id=c, text=t, parse_mode='HTML', **k)

def sdoc(c, data, fn, cap=''):
    try:
        return requests.post(
            TG + '/sendDocument',
            data={'chat_id': c, 'caption': cap, 'parse_mode': 'HTML'},
            files={'document': (fn, data, 'text/html')}, timeout=60).json()
    except Exception as e:
        return {'error': str(e)}

def gql(tok, op, q, v=None):
    h = {
        'accept': '*/*',
        'content-type': 'application/json',
        'authorization': 'Bearer ' + tok,
        'user-agent': UA
    }
    try:
        r = requests.post(HJ, headers=h,
            json={'operationName': op, 'variables': v or {}, 'query': q}, timeout=30)
        d = r.json()
        return d.get('data', {}), d.get('errors', [])
    except Exception as e:
        return {}, [{'message': str(e)}]

def sms(p):
    h = {'accept': '*/*', 'content-type': 'application/json', 'user-agent': UA}
    q = 'mutation getVerificationCode($phoneNumber: String!) '
    q += '{ getVerificationCode(phoneNumber: $phoneNumber) { status } }'
    try:
        r = requests.post(HJ, headers=h, json={
            'operationName': 'getVerificationCode',
            'variables': {'phoneNumber': p},
            'query': q}, timeout=15)
        result = (r.json().get('data') or {}).get('getVerificationCode', {})
        return result.get('status', '') == 'ok'
    except:
        return False

def vcode(p, c):
    h = {'accept': '*/*', 'content-type': 'application/json', 'user-agent': UA}
    q = 'mutation verifyPhoneNumberWithCode($input: CodeInput!) '
    q += '{ verifyPhoneNumberWithCode(input: $input) { status token } }'
    try:
        r = requests.post(HJ, headers=h, json={
            'operationName': 'verifyPhoneNumberWithCode',
            'variables': {'input': {'code': c, 'phoneNumber': p}},
            'query': q}, timeout=15)
        res = (r.json().get('data') or {}).get('verifyPhoneNumberWithCode', {})
        return res.get('token', '') if res.get('status') == '200' else None
    except:
        return None

def build_trainer_bars(btr):
    tbars = ''
    if not btr:
        return tbars
    mx = btr.most_common(1)[0][1]
    for t, c in btr.most_common(6):
        p = round(c / mx * 100)
        tbars += '<div style="margin-bottom:10px">'
        tbars += '<div style="display:flex;justify-content:space-between;font-size:13px;font-weight:600;margin-bottom:3px">'
        tbars += '<span>' + t + '</span>'
        tbars += '<span style="color:#2d5a27">' + str(c) + '</span></div>'
        tbars += '<div style="height:5px;background:#e8e4dd;border-radius:3px;overflow:hidden">'
        tbars += '<div style="height:100%;width:' + str(p) + '%;background:linear-gradient(90deg,#2d5a27,#a8d9a0);border-radius:3px"></div>'
        tbars += '</div></div>'
    return tbars

def build_insight(cls, icon, title, text):
    colors = {
        'green': ('#edf7f0', '#c3e6cc', '#2d7d46'),
        'yellow': ('#fef9ee', '#fde9b8', '#b07800'),
        'red': ('#fdf2f1', '#f5c6c3', '#c0392b'),
        'blue': ('#edf2f9', '#c3d5ed', '#1e4d8c')
    }
    bg, bd, tc = colors.get(cls, colors['blue'])
    html = '<div style="display:flex;gap:12px;background:' + bg + ';border:1px solid ' + bd + ';border-radius:12px;padding:14px;margin-bottom:10px">'
    html += '<div style="font-size:20px;flex-shrink:0">' + icon + '</div>'
    html += '<div>'
    html += '<div style="font-size:13px;font-weight:700;color:' + tc + ';margin-bottom:3px">' + title + '</div>'
    html += '<div style="font-size:12px;color:#1a1a1a;line-height:1.55">' + text + '</div>'
    html += '</div></div>'
    return html

def gen(tok, uid, name):
    q_user = 'query getCurrentUser { getCurrentUser { '
    q_user += 'id nickname firstName points dumbbells level { name } '
    q_user += 'club { name } heroPass { availableCount endTime heroPass { name } } } }'
    pd, _ = gql(tok, 'getCurrentUser', q_user)
    u = pd.get('getCurrentUser') or {}

    q_book = 'query userBookings($userId: ID) { userBookings(userId: $userId) { '
    q_book += 'id status event { startTime programSet { name type } trainer { nickname } club { name } } } }'
    bd, _ = gql(tok, 'userBookings', q_book, {'userId': uid})
    ab = bd.get('userBookings') or []
    att = [b for b in ab if b.get('status') == 'attended']
    can = [b for b in ab if b.get('status') == 'canceled']

    rows = []
    for b in att:
        ev = b.get('event') or {}
        ps = ev.get('programSet') or {}
        tr = ev.get('trainer') or {}
        cl = ev.get('club') or {}
        s = ev.get('startTime', '')
        try:
            dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
            rows.append({
                'date': dt.strftime('%Y-%m-%d'),
                'month': dt.strftime('%Y-%m'),
                'wd': dt.strftime('%A'),
                'h': dt.hour,
                'prog': ps.get('name', ''),
                'type': ps.get('type', ''),
                'tr': tr.get('nickname', ''),
                'cl': cl.get('name', '')
            })
        except:
            pass
    rows.sort(key=lambda x: x['date'])

    bm = Counter(r['month'] for r in rows if r['month'])
    bt = Counter(r['type'] for r in rows if r['type'])
    btr = Counter(r['tr'] for r in rows if r['tr'])
    bwd = Counter(r['wd'] for r in rows)
    bh = Counter(r['h'] for r in rows)
    ms = sorted(bm.items())
    wdo = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    wr = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    wd = [bwd.get(d, 0) for d in wdo]
    bmo = max(bm.items(), key=lambda x: x[1]) if bm else ('—', 0)
    tt = btr.most_common(1)[0] if btr else ('—', 0)
    tp = bt.most_common(1)[0] if bt else ('—', 0)
    ph = max(bh.items(), key=lambda x: x[1])[0] if bh else 8
    cr = round(len(can) / len(ab) * 100, 1) if ab else 0
    ar = round(len(att) / len(ab) * 100, 1) if ab else 0
    apw = round(len(att) / max(len(ms) * 4.3, 1), 1)
    tm = {
        'fullBody': 'Full Body', 'push': 'Push', 'pull': 'Pull',
        'legs': 'Legs', 'gluteLab': 'Glute Lab', 'bootcamp': 'Bootcamp',
        'armBlast': 'Arm Blast', 'metcon': 'Metcon', 'upperBody': 'Upper Body'
    }
    nick = u.get('nickname') or u.get('firstName') or name
    lvl = (u.get('level') or {}).get('name', '—')
    cl_ = (u.get('club') or {}).get('name', '—')
    hp = u.get('heroPass') or {}
    hpl = hp.get('availableCount', 0) or 0
    hpe = hp.get('endTime', '')
    try:
        hpf = datetime.fromisoformat(hpe.replace('Z', '+00:00')).strftime('%d.%m.%Y') if hpe else '—'
    except:
        hpf = '—'
    hp_name = (hp.get('heroPass') or {}).get('name') or 'Hero Pass'
    fw = rows[0]['date'] if rows else '—'
    lw = rows[-1]['date'] if rows else '—'
    gd = datetime.now().strftime('%d.%m.%Y')
    gr = 'A' if ar >= 80 else 'B+' if ar >= 65 else 'B' if ar >= 55 else 'C+'
    gt = 'Отличная дисциплина!' if ar >= 80 else 'Хорошая база, есть куда расти' if ar >= 55 else 'Нужно добавить стабильности'
    mv = [m[1] for m in ms]
    tpl = tm.get(tp[0], tp[0])
    tbars = build_trainer_bars(btr)

    ih = ''
    if cr > 35:
        ih += build_insight('yellow', '⚠️', 'Высокий процент отмен', str(cr) + '% записей отменяются — записывайся только когда уверен.')
    else:
        ih += build_insight('green', '✅', 'Хорошая дисциплина', 'Только ' + str(cr) + '% отмен — отличная стабильность!')
    if apw >= 3:
        ih += build_insight('green', '💪', 'Оптимальная частота', str(apw) + ' тренировок/нед — золотой стандарт!')
    elif apw >= 2:
        ih += build_insight('yellow', '📅', 'Можно чаще', str(apw) + ' тренировок/нед — добавь одно занятие.')
    else:
        ih += build_insight('red', '🔔', 'Низкая частота', str(apw) + ' тренировок/нед — слишком мало.')
    morning = 'Утренние — буст на день!'
    daytime = 'Дневные идеальны для силы.'
    ih += build_insight('blue', '🌅', 'Время тренировок', 'Пик в ' + str(ph) + ':00. ' + (morning if ph < 12 else daytime))
    if tt[0] != '—':
        ih += build_insight('green', '🤝', 'Тренер ' + tt[0], str(tt[1]) + ' тренировок вместе — постоянный тренер ускоряет прогресс!')

    tr_html = ''
    for r in reversed(rows[-40:]):
        tr_html += '<tr>'
        tr_html += '<td style="white-space:nowrap">' + r['date'] + '</td>'
        tr_html += '<td>' + r['prog'] + '</td>'
        tr_html += '<td>' + r['tr'] + '</td>'
        tr_html += '<td style="color:#6b6b6b">' + r['cl'] + '</td>'
        tr_html += '</tr>'

    if ar >= 80:
        sum_text = 'Посещаемость 80%+ — настоящая дисциплина!'
    elif ar >= 55:
        sum_text = 'Посещаемость ' + str(ar) + '% — снизь отмены и прогресс ускорится.'
    else:
        sum_text = '3 твёрдые тренировки лучше 5 записей и 2 посещений.'

    m_labels = json.dumps([m[0] for m in ms], ensure_ascii=False)
    m_vals = json.dumps(mv)
    wd_vals = json.dumps(wd)
    wr_labels = json.dumps(wr, ensure_ascii=False)
    t_labels = json.dumps([tm.get(k, k) for k, _ in bt.most_common(7)], ensure_ascii=False)
    t_vals = json.dumps([v for _, v in bt.most_common(7)])
    mv_max = 'Math.max(...mv)'
    wv_max = 'Math.max(...wv)'

    css = '''
@import url(https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap);
*{box-sizing:border-box;margin:0;padding:0}
body{background:#f8f7f4;color:#1a1a1a;font-family:Inter,-apple-system,sans-serif;line-height:1.6}
.hero{background:linear-gradient(135deg,#1a2f16,#2d5a27,#1a3a28);color:#fff;padding:44px 0 52px;overflow:hidden}
.inner,.wrap{max-width:840px;margin:0 auto;padding:0 24px}
.badge{display:inline-flex;align-items:center;gap:6px;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.2);border-radius:100px;padding:5px 14px;font-size:12px;font-weight:500;margin-bottom:16px}
.hero h1{font-size:30px;font-weight:800;line-height:1.2;margin-bottom:6px}
.hero h1 span{color:#a8d9a0}
.hero-sub{font-size:12px;color:rgba(255,255,255,.6);margin-bottom:22px}
.hs{display:flex;gap:22px;flex-wrap:wrap}
.hs-v{font-size:22px;font-weight:800;color:#a8d9a0}.hs-l{font-size:11px;color:rgba(255,255,255,.55);margin-top:1px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:-22px}
.kpi{background:#fff;border-radius:12px;box-shadow:0 4px 20px rgba(0,0,0,.08);border:1px solid #e8e4dd;padding:15px}
.ki{font-size:18px;margin-bottom:6px}.kv{font-size:20px;font-weight:800;line-height:1;margin-bottom:2px}
.kl{font-size:11px;color:#6b6b6b}.ks{font-size:10px;color:#6b6b6b;margin-top:2px}
.sec{padding:22px 0 0}
.sl{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:#2d5a27;margin-bottom:4px}
.st{font-size:20px;font-weight:800;margin-bottom:3px}.ss{font-size:12px;color:#6b6b6b;margin-bottom:14px}
.card{background:#fff;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,.05);border:1px solid #e8e4dd;padding:16px}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.ct{font-size:13px;font-weight:700;margin-bottom:2px}.cs{font-size:11px;color:#6b6b6b;margin-bottom:12px}
.cw{position:relative}.tw{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:left;padding:7px 10px;color:#6b6b6b;font-weight:600;text-transform:uppercase;font-size:10px;letter-spacing:.5px;border-bottom:2px solid #e8e4dd}
td{padding:8px 10px;border-bottom:1px solid #e8e4dd}tr:hover td{background:#fafaf8}
.sum{background:linear-gradient(135deg,#e8f0e6,#f8f7f4);border:1px solid #c3e6cc;border-radius:12px;padding:16px;margin-top:12px}
.grade{display:inline-block;background:#2d5a27;color:#fff;border-radius:10px;padding:5px 16px;font-size:24px;font-weight:900;margin-right:12px;vertical-align:middle}
.hp-box{background:#edf7f0;border:1px solid #c3e6cc;border-radius:10px;padding:10px 14px;display:flex;align-items:center;gap:10px;margin-bottom:12px}
.footer{margin-top:28px;padding:16px 0;border-top:1px solid #e8e4dd;text-align:center;color:#6b6b6b;font-size:11px}
@media(max-width:600px){.kpis{grid-template-columns:repeat(2,1fr)}.g2{grid-template-columns:1fr}.hero h1{font-size:22px}.inner,.wrap{padding:0 14px}}
'''

    h = '<!DOCTYPE html><html lang="ru"><head>'
    h += '<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    h += '<title>Отчёт — ' + nick + '</title>'
    h += '<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>'
    h += '<style>' + css + '</style>'
    h += '</head><body>'
    h += '<div class="hero"><div class="inner">'
    h += '<div class="badge">⚔️ Hero\'s Journey · Персональный отчёт</div>'
    h += '<h1>Твои тренировки,<br><span>' + nick + '</span></h1>'
    h += '<p class="hero-sub">' + lvl + ' · ' + cl_ + ' · ' + fw + ' — ' + lw + '</p>'
    h += '<div class="hs">'
    h += '<div><div class="hs-v">' + str(len(att)) + '</div><div class="hs-l">Тренировок</div></div>'
    h += '<div><div class="hs-v">' + str(len(ab)) + '</div><div class="hs-l">Записей</div></div>'
    h += '<div><div class="hs-v">' + str(ar) + '%</div><div class="hs-l">Посещаемость</div></div>'
    h += '<div><div class="hs-v">' + str(hpl) + '</div><div class="hs-l">Визитов осталось</div></div>'
    h += '</div></div></div>'
    h += '<div class="wrap">'
    h += '<div class="kpis">'
    h += '<div class="kpi"><div class="ki">📅</div><div class="kv">' + str(apw) + '</div><div class="kl">Тренировок/нед.</div></div>'
    h += '<div class="kpi"><div class="ki">🏆</div><div class="kv">' + str(bmo[1]) + '</div><div class="kl">Лучший месяц</div><div class="ks">' + bmo[0] + '</div></div>'
    h += '<div class="kpi"><div class="ki">❌</div><div class="kv">' + str(cr) + '%</div><div class="kl">Отмен</div></div>'
    h += '<div class="kpi"><div class="ki">🤝</div><div class="kv">' + str(tt[1]) + '</div><div class="kl">' + tt[0] + '</div></div>'
    h += '</div>'
    h += '<div class="sec"><div class="sl">Абонемент</div>'
    h += '<div class="hp-box"><div style="font-size:22px">🎫</div><div>'
    h += '<div style="font-size:14px;font-weight:700">' + hp_name + '</div>'
    h += '<div style="font-size:12px;color:#6b6b6b">Визитов: <b style="color:#2d5a27">' + str(hpl) + '</b> · До: <b>' + hpf + '</b></div>'
    h += '</div></div></div>'
    h += '<div class="sec"><div class="sl">01 — Активность</div><div class="st">Динамика</div><div class="ss">По месяцам и дням</div>'
    h += '<div class="g2">'
    h += '<div class="card"><div class="ct">По месяцам</div><div class="cs">Посещённые тренировки</div><div class="cw" style="height:170px"><canvas id="cM"></canvas></div></div>'
    h += '<div class="card"><div class="ct">По дням недели</div><div class="cs">Когда чаще</div><div class="cw" style="height:170px"><canvas id="cW"></canvas></div></div>'
    h += '</div></div>'
    h += '<div class="sec"><div class="sl">02 — Структура</div><div class="st">Типы и тренеры</div><div class="ss">Состав программы</div>'
    h += '<div class="g2">'
    h += '<div class="card"><div class="ct">Типы тренировок</div><div class="cs">Доли программ</div><div class="cw" style="height:190px"><canvas id="cT"></canvas></div></div>'
    h += '<div class="card"><div class="ct">Топ тренеров</div><div class="cs">Совместных занятий</div><div style="margin-top:6px">' + tbars + '</div></div>'
    h += '</div></div>'
    h += '<div class="sec"><div class="sl">03 — Инсайты</div><div class="st">Что говорят данные</div><div class="ss">Анализ</div>' + ih + '</div>'
    h += '<div class="sec"><div class="sl">04 — История</div><div class="st">Последние 40 тренировок</div>'
    h += '<div class="card"><div class="tw"><table><thead><tr>'
    h += '<th>Дата</th><th>Программа</th><th>Тренер</th><th>Клуб</th>'
    h += '</tr></thead><tbody>' + tr_html + '</tbody></table></div></div></div>'
    h += '<div class="sec"><div class="sl">05 — Итог</div><div class="st">Общая оценка</div>'
    h += '<div class="sum">'
    h += '<div style="display:flex;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:10px">'
    h += '<span class="grade">' + gr + '</span>'
    h += '<div><div style="font-size:16px;font-weight:800;color:#2d5a27">' + gt + '</div>'
    h += '<div style="font-size:11px;color:#6b6b6b;margin-top:2px">' + lvl + ' · ' + str(len(ms)) + ' мес.</div></div></div>'
    h += '<div style="font-size:12px;line-height:1.65">За ' + str(len(ms)) + ' мес. ты посетил <b>' + str(len(att)) + ' тренировок</b> из ' + str(len(ab)) + '. '
    h += sum_text + ' Топ тренер — <b>' + tt[0] + '</b>, тип — <b>' + tpl + '</b>.</div>'
    h += '</div></div>'
    h += '</div>'
    h += '<div class="footer"><div class="wrap">Отчёт ' + gd + ' · HJ Analytics Bot · ' + str(len(att)) + ' тренировок</div></div>'

    js = '<script>'
    js += 'Chart.defaults.font.family="Inter,sans-serif";Chart.defaults.color="#6b6b6b";'
    js += 'var mv=' + m_vals + ';'
    js += 'new Chart(document.getElementById("cM"),{type:"bar",data:{labels:' + m_labels + ',datasets:[{data:mv,backgroundColor:mv.map(v=>v===' + mv_max + '?"#2d5a27":"#a8d9a0"),borderRadius:6,borderSkipped:false}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{display:false},ticks:{maxRotation:45,font:{size:10}}},y:{grid:{color:"#e8e4dd"}}}}});'
    js += 'var wv=' + wd_vals + ';'
    js += 'new Chart(document.getElementById("cW"),{type:"bar",data:{labels:' + wr_labels + ',datasets:[{data:wv,backgroundColor:wv.map(v=>v===' + wv_max + '?"#2d5a27":"#d4e8d1"),borderRadius:6,borderSkipped:false}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{display:false}},y:{grid:{color:"#e8e4dd"}}}}});'
    js += 'new Chart(document.getElementById("cT"),{type:"doughnut",data:{labels:' + t_labels + ',datasets:[{data:' + t_vals + ',backgroundColor:["#2d5a27","#a8d9a0","#c8512a","#f5a623","#1e4d8c","#60a5fa","#c084fc"],borderWidth:3,borderColor:"#fff"}]},options:{responsive:true,maintainAspectRatio:false,cutout:"55%",plugins:{legend:{position:"right",labels:{font:{size:11},boxWidth:12}}}}});'
    js += '</script>'
    h += js + '</body></html>'
    return h


def handle(msg):
    cid = msg['chat']['id']
    text = msg.get('text', '').strip()
    fn = msg.get('from', {}).get('first_name', 'Герой')
    st = states.get(cid, {})

    if text in ['/start', '/help']:
        states[cid] = {'state': 'idle'}
        welcome = '🏋️ <b>Hero\'s Journey Analytics</b>\n\n'
        welcome += 'Привет, ' + fn + '!\n\n'
        welcome += '📊 Персональный HTML-отчёт по тренировкам:\n'
        welcome += '• Динамика по месяцам\n'
        welcome += '• Типы нагрузок и тренеры\n'
        welcome += '• Посещаемость и инсайты\n'
        welcome += '• История 40 последних занятий\n'
        welcome += '• Оценка и рекомендации\n\n'
        welcome += '📱 Введи номер из Hero\'s Journey:\n'
        welcome += '<i>Например: 87771234567</i>'
        tg('sendMessage', chat_id=cid, parse_mode='HTML', text=welcome,
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
                send(cid, '❌ Номер <b>' + disp + '</b> не найден. Проверь номер.')
                states[cid] = {'state': 'idle'}
            return

    if st.get('state') == 'waiting_code':
        if text.isdigit() and len(text) == 4:
            hj = st.get('phone', '')
            send(cid, '⏳ Авторизуюсь и собираю данные...\nЭто займёт ~30 секунд 🔄')
            tok = vcode(hj, text)
            if not tok:
                send(cid, '❌ Неверный код. Напиши /start.')
                states[cid] = {'state': 'idle'}
                return
            pd, _ = gql(tok, 'getCurrentUser', 'query getCurrentUser { getCurrentUser { id nickname firstName } }')
            u = pd.get('getCurrentUser') or {}
            uid = u.get('id', '')
            fname = u.get('firstName') or u.get('nickname') or fn
            send(cid, '✅ Привет, <b>' + fname + '</b>!\n\n📊 Генерирую отчёт...')
            try:
                html = gen(tok, uid, fname)
                fs = fname.lower().replace(' ', '_')
                res = sdoc(cid, html.encode('utf-8'), 'hj_' + fs + '.html',
                          '🎉 <b>Готово, ' + fname + '!</b>\n\nОткрой в браузере.\n\n/start — обновить.')
                if res.get('error'):
                    send(cid, '⚠️ ' + str(res['error']))
            except Exception as e:
                send(cid, '⚠️ Ошибка: ' + str(e)[:200] + '\n\nНапиши /start.')
            states[cid] = {'state': 'idle'}
        else:
            send(cid, 'Жду 4-значный код. /start — начать заново.')
        return

    send(cid, 'Напиши /start',
         reply_markup={'keyboard': [[{'text': '📱 Поделиться номером', 'request_contact': True}]],
                       'resize_keyboard': True, 'one_time_keyboard': True})


# Main loop
offset = 0
tg('setMyCommands', commands=[
    {'command': 'start', 'description': 'Получить отчёт'},
    {'command': 'help', 'description': 'Помощь'}
])
try:
    u = requests.get(TG + '/getUpdates', params={'offset': -1, 'timeout': 1}, timeout=5).json()
    if u.get('result'):
        offset = u['result'][-1]['update_id'] + 1
except:
    pass
print('✅ HJ Analytics Bot running!')
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
                    try:
                        handle(msg)
                    except Exception as e:
                        c = msg.get('chat', {}).get('id')
                        if c:
                            send(c, '⚠️ Ошибка. Напиши /start.')
    except:
        time.sleep(3)