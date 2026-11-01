# 🎬 Video montaj buyurtma boti

Mijoz botga kirib to'lov qiladi, chek va videolarini yuboradi. Hammasi sizning kanalingizga tushadi
(✅ Tasdiqlash / ❌ Rad etish tugmalari bilan). Montajdan keyin tayyor videoni bot orqali mijozga yuborasiz.

## Railway'ga joylash

1. Papkani GitHub'ga yuklang (yangi repo → hamma fayllarni push qiling).
2. Railway → **New Project → Deploy from GitHub repo** → shu repoNI tanlang.
3. **Variables** bo'limiga qo'shing:

| Nomi | Qiymati |
|---|---|
| `BOT_TOKEN` | @BotFather bergan token |
| `ADMIN_IDS` | Sizning Telegram ID'ingiz (bir nechta bo'lsa vergul bilan: `111,222`) |
| `CHANNEL_ID` | Buyurtmalar tushadigan kanal ID'si (`-100...`) |
| `DATA_DIR` | `/data` |

4. **Volume** qo'shing: servis → **Settings → Volumes → Add Volume** → Mount path: `/data`
   (shunda baza — foydalanuvchilar, buyurtmalar, sozlamalar — qayta deploy qilganda o'chib ketmaydi).
5. Deploy tugagach botga `/start`, adminga `/admin` yozing.

## Kanalni tayyorlash

1. Yangi **private kanal** yarating (buyurtmalar shu yerga tushadi).
2. Botni kanalga **admin** qiling (xabar yuborish huquqi bilan).
3. Kanal ID'sini olish: kanaldan biror postni **@userinfobot** yoki **@getidsbot** ga forward qiling → `-100...` ko'rinishidagi ID.
4. Telegram ID'ingizni olish: @userinfobot ga `/start` yozing.

## Admin panel (`/admin`)

- 📊 **Statistika** — foydalanuvchilar, buyurtmalar, tushum (bugun / oy / jami)
- 📋 **Buyurtmalar** — ro'yxat, chek va videolarni ko'rish, tasdiqlash/rad etish, tayyor video yuborish
- 📣 **Xabar yuborish** — barcha foydalanuvchilarga (matn, rasm, video)
- 📢 **Majburiy obuna** — reklama tushsa kanalni qo'shasiz (bot o'sha kanalda admin bo'lishi shart)
- 💰 **Narx**, 💳 **Karta** — istalgan vaqtda o'zgartirasiz
- ✏️ **Matnlar** — hamma xabar matnlari va tugma nomi (qalin/kursiv saqlanadi)
- 🖼 **Rasmlar** — boshlang'ich va to'lov sahifasiga rasm
- 🟢/🔴 Buyurtma qabul qilishni vaqtincha to'xtatish

Matnlarda ishlatiladigan belgilar: `{price}` narx, `{card}` karta, `{holder}` karta egasi, `{id}` buyurtma raqami.

## Tayyor videoni yuborish

Kanaldagi buyurtma ostidagi **📤 Tayyor videoni yuborish** tugmasi (tasdiqlangandan keyin chiqadi) → bot lichkasiga
videoni tashlang → **✅ Yakunlash**. Video mijozga bot nomidan boradi.

## Mahalliy ishga tushirish

```bash
pip install -r requirements.txt
export BOT_TOKEN=... ADMIN_IDS=... CHANNEL_ID=...
python bot.py
```
