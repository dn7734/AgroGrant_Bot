/**
 * НАУКОВО-МЕТОДИЧНИЙ ОПИС МОДУЛЯ (AgroGrant_Bot / script.js):
 * Клієнтське ядро грантового чат-бота.
 * Виправлено дублювання голосового вводу Web Speech API на ОС Android
 * (continuous = false, interimResults = false) та реалізовано прийом параметрів ?data= з платформи Кластеру.
 */

document.addEventListener("DOMContentLoaded", () => {
	const BACKEND_URL = "https://agrogrant.onrender.com";
	let serverLoggingAvailable = true;

	const COMPANIES_DB = {
		"03728915": {
			edrpou: "03728915",
			company_name: "ФГ «ПОДІЛЬСЬКИЙ КОЛОС»",
			kved: "01.11 Вирощування зернових і технічних культур",
			region: "Вінницька область",
			activity_type: "Рослинництво, насінництво гірчиці та зернових",
			size_category: "300 га",
			own_contribution_percent: "30%",
			investment_focus: "Масштабування посівів та первинна переробка зерна"
		},
		"38492014": {
			edrpou: "38492014",
			company_name: "ТОВ «ПОДІЛЛЯ-САД ІНВЕСТ»",
			kved: "01.24 Вирощування зерняткових і кісточкових фруктів",
			region: "Вінницька область",
			activity_type: "Інтенсивне садівництво та ягідництво",
			size_category: "25 га саду",
			own_contribution_percent: "30%",
			investment_focus: "Закладання інтенсивного саду та систем крапельного зрошення"
		},
		"41258963": {
			edrpou: "41258963",
			company_name: "ТОВ «АГРО-ЕКО ПЕРЕРОБКА»",
			kved: "10.41 Виробництво олії та тваринних жирів",
			region: "Черкаська область",
			activity_type: "Глибока переробка аграрної сировини",
			size_category: "Виробничий цех до 1500 т/рік",
			own_contribution_percent: "35%",
			investment_focus: "Лінія холодного пресування олії, виробництво порошку та шроту"
		},
		"00496802": {
			edrpou: "00496802",
			company_name: "ННЦ «ІНСТИТУТ ЗЕМЛЕРОБСТВА НААН»",
			kved: "72.19 Дослідження й експериментальні розробки",
			region: "Київська область, смт Чабани",
			activity_type: "Наукове ядро кластеру та селекція",
			size_category: "Розсадник супереліти 1–15 га",
			own_contribution_percent: "25%",
			investment_focus: "Трансфер сорту гірчиці «Біла Принцеса» у промисловий кластер"
		}
	};

	const GRANTS_CATALOG = [
		{
			title: "Державний грант на створення або розвиток переробних підприємств (єРобота)",
			donor: "Мінекономіки України / Дія.Бізнес",
			max_amount: "до 8 000 000 грн",
			min_own: 20,
			kveds: ["10.41", "10.61", "01.11", "72.19"],
			keywords: ["перероб", "олія", "лінія", "кластер", "шрот", "зерн"]
		},
		{
			title: "Грантова програма підтримки садівництва, ягідництва та тепличного господарства",
			donor: "Мінагрополітики / ДАР",
			max_amount: "до 10 000 000 грн (до 400 тис. грн/га)",
			min_own: 30,
			kveds: ["01.24", "01.25", "01.13"],
			keywords: ["сад", "зрошен", "теплиц", "ягід"]
		},
		{
			title: "Програма USAID АГРО: Співфінансування модернізації елеваторів, насінництва та переробки",
			donor: "USAID АГРО",
			max_amount: "до 15 000 000 грн",
			min_own: 30,
			kveds: ["01.11", "01.64", "10.41", "72.19"],
			keywords: ["насін", "гірчиц", "біла принцеса", "перероб", "маржа", "кластер"]
		},
		{
			title: "Мікрогрант «Власна справа» для малих фермерських господарств та кооперативів",
			donor: "Державна служба зайнятості",
			max_amount: "до 250 000 – 500 000 грн",
			min_own: 0,
			kveds: ["01.11", "01.24", "10.41"],
			keywords: ["фермер", "обладнан", "старт", "посів"]
		}
	];

	let currentProfile = { ...COMPANIES_DB["03728915"] };
	let currentScoredGrants = [];

	async function logAction(actionName, detailsStr) {
		const entry = { timestamp: new Date().toLocaleString('uk-UA'), action: actionName, details: detailsStr };
		try {
			const localLogs = JSON.parse(localStorage.getItem('agrogrant_logs') || '[]');
			localLogs.unshift(entry);
			localStorage.setItem('agrogrant_logs', JSON.stringify(localLogs.slice(0, 100)));
		} catch (err) { }

		if (!serverLoggingAvailable) return;
		try {
			const res = await fetch(`${BACKEND_URL}/log`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ action: actionName, details: detailsStr })
			});
			if (res.status === 404) serverLoggingAvailable = false;
		} catch (e) {
			serverLoggingAvailable = false;
		}
	}

	function scoreAndRenderGrants() {
		const text = `${currentProfile.kved} ${currentProfile.activity_type} ${currentProfile.investment_focus}`.toLowerCase();
		const ownNum = parseFloat(currentProfile.own_contribution_percent) || 30;

		currentScoredGrants = GRANTS_CATALOG.map(g => {
			let s = 60;
			if (g.keywords.some(kw => text.includes(kw))) s += 22;
			if (g.kveds.some(kv => currentProfile.kved.includes(kv))) s += 10;
			if (ownNum >= g.min_own) s += 6;
			else s -= 8;
			return { ...g, score: Math.min(98, Math.max(40, s)) };
		}).sort((a, b) => b.score - a.score);

		const container = document.getElementById('grantsContainer');
		container.innerHTML = currentScoredGrants.map(g => `
            <div class="grant-item">
                <div class="grant-head">
                    <span class="grant-title">${g.title}</span>
                    <span class="grant-score">Відповідність: ${g.score}%</span>
                </div>
                <div class="grant-meta">
                    <strong>Донор:</strong> ${g.donor} | <strong>Сума:</strong> ${g.max_amount} | <strong>Власний внесок:</strong> від ${g.min_own}%
                </div>
            </div>
        `).join('');
	}

	function updateProfileUI(prof) {
		currentProfile = prof;
		document.getElementById('p_edrpou').textContent = prof.edrpou;
		document.getElementById('p_region').textContent = prof.region;
		document.getElementById('p_company').textContent = prof.company_name;
		document.getElementById('p_kved').textContent = prof.kved;
		document.getElementById('p_size').textContent = prof.size_category;
		document.getElementById('p_own').textContent = prof.own_contribution_percent;
		document.getElementById('p_focus').textContent = prof.investment_focus;
		scoreAndRenderGrants();
	}

	const chatbox = document.getElementById('chatbox');
	function addChatMsg(sender, htmlText) {
		const div = document.createElement('div');
		div.className = 'msg ' + (sender === 'Ви' ? 'user' : 'bot');
		div.innerHTML = `<strong>${sender}:</strong><br>${htmlText}`;
		chatbox.appendChild(div);
		chatbox.scrollTop = chatbox.scrollHeight;
	}

	async function processMessage(rawText) {
		const clean = rawText.trim();
		if (!clean) return;
		addChatMsg('Ви', clean);

		const match = clean.match(/\b(\d{8})\b/);
		const code = match ? match[1] : null;

		if (code && COMPANIES_DB[code]) {
			updateProfileUI({ ...COMPANIES_DB[code], investment_focus: clean });
			logAction('EDRPOU_MATCH', `Code: ${code}`);
		} else if (code) {
			updateProfileUI({
				edrpou: code,
				company_name: `АГРОПІДПРИЄМСТВО (ЄДРПОУ ${code})`,
				kved: "01.11 / 10.41 Агровиробництво та переробка",
				region: "Україна",
				activity_type: "Аграрне виробництво",
				size_category: "300 га",
				own_contribution_percent: "30%",
				investment_focus: clean
			});
			logAction('EDRPOU_NEW', `Code: ${code}`);
		} else {
			currentProfile.investment_focus = clean;
			updateProfileUI(currentProfile);
			logAction('USER_QUERY', clean);
		}

		const topGrant = currentScoredGrants[0];
		addChatMsg(
			'AgroGrant',
			`Дані підприємства <strong>${currentProfile.company_name}</strong> (ЄДРПОУ ${currentProfile.edrpou}) проаналізовано.<br>` +
			`• Найбільш релевантна програма: <strong>${topGrant.title}</strong> (${topGrant.score}% збігу, ${topGrant.max_amount}).<br>` +
			`• Ви можете завантажити готовий аналітичний звіт у PDF або DOCX.`
		);
	}

	// КРОСПЛАТФОРМНИЙ ГОЛОСОВИЙ ВВІД (БЕЗ ДУБЛЮВАННЯ "ДРАБИНКОЮ" НА ANDROID)
	const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
	const voiceBtn = document.getElementById('voiceBtn');

	if (SpeechRecognition && voiceBtn) {
		const recognition = new SpeechRecognition();
		recognition.lang = 'uk-UA';
		recognition.continuous = false;
		recognition.interimResults = false;

		voiceBtn.addEventListener('click', () => {
			try {
				voiceBtn.textContent = 'Слухаю...';
				recognition.start();
			} catch (e) {
				voiceBtn.textContent = 'Голос';
			}
		});

		recognition.onresult = (event) => {
			const lastIdx = event.results.length - 1;
			const transcript = event.results[lastIdx][0].transcript.trim();
			const inputEl = document.getElementById('textInput');

			// КРИТИЧНЕ ВИПРАВЛЕННЯ: Додаємо новий текст до існуючого через пробіл, а не затираємо
			if (inputEl.value.trim().length > 0) {
				inputEl.value = inputEl.value.trim() + ' ' + transcript;
			} else {
				inputEl.value = transcript;
			}

			voiceBtn.textContent = 'Голос';
			// Логування не зламає запит, навіть якщо сервер спить
			logAction('VOICE_INPUT', transcript);
		};

		recognition.onerror = () => { voiceBtn.textContent = 'Голос'; };
		recognition.onend = () => { voiceBtn.textContent = 'Голос'; };
	} else if (voiceBtn) {
		voiceBtn.style.display = 'none';
	}

	document.getElementById('sendBtn').addEventListener('click', () => {
		const inp = document.getElementById('textInput');
		processMessage(inp.value);
		inp.value = '';
	});

	document.getElementById('textInput').addEventListener('keydown', (e) => {
		if (e.key === 'Enter') {
			processMessage(e.target.value);
			e.target.value = '';
		}
	});

	document.querySelectorAll('.chip[data-query]').forEach(btn => {
		btn.addEventListener('click', () => processMessage(btn.getAttribute('data-query')));
	});

	document.getElementById('resetSessionBtn').addEventListener('click', () => {
		chatbox.innerHTML = '<div class="msg bot"><strong>AgroGrant:</strong><br>Сесію очищено. Введіть код ЄДРПОУ або оберіть приклад вище.</div>';
		updateProfileUI({ ...COMPANIES_DB["03728915"] });
		logAction('SESSION_RESET', 'Cleared by user');
	});

	// Перевірка вхідного мосту ?data=... з платформи AgroCluster Analytics
	const urlParams = new URLSearchParams(window.location.search);
	const bridgeData = urlParams.get('data');
	if (bridgeData) {
		processMessage(bridgeData);
		logAction('BRIDGE_RECEIVED', bridgeData);
	} else {
		scoreAndRenderGrants();
	}

	// Експорт PDF методом Viewport Overlay
	document.getElementById('downloadPdfBtn').addEventListener('click', async () => {
		const btn = document.getElementById('downloadPdfBtn');
		const orig = btn.textContent;
		btn.disabled = true;
		btn.textContent = 'Формую PDF...';
		logAction('PDF_REPORT_EXPORT', `EDRPOU: ${currentProfile.edrpou}`);

		const wrapper = document.getElementById('pdfOverlayWrapper');
		const target = document.getElementById('pdfRenderTarget');
		const prevY = window.scrollY;

		target.innerHTML = `
            <div style="border-bottom: 3px solid #059669; padding-bottom: 10px; margin-bottom: 14px;">
                <h2 style="margin: 0; font-size: 17px; color: #0f172a;">АНАЛІТИЧНИЙ ЗВІТ ОЦІНКИ ГРАНТОСПРОМОЖНОСТІ ПІДПРИЄМСТВА</h2>
                <p style="margin: 4px 0 0 0; font-size: 11px; color: #475569;">Дата: ${new Date().toLocaleDateString('uk-UA')} | Інтелектуальна система AgroGrant Analytics</p>
            </div>
            <h3 style="font-size: 13.5px; color: #059669;">1. Реєстраційний профіль заявника</h3>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 14px; font-size: 11.5px;">
                <tr><td style="border: 1px solid #cbd5e1; padding: 6px; font-weight: bold; width: 35%; background: #f8fafc;">Підприємство (ЄДРПОУ)</td><td style="border: 1px solid #cbd5e1; padding: 6px;">${currentProfile.company_name} (${currentProfile.edrpou})</td></tr>
                <tr><td style="border: 1px solid #cbd5e1; padding: 6px; font-weight: bold; background: #f8fafc;">КВЕД та Регіон</td><td style="border: 1px solid #cbd5e1; padding: 6px;">${currentProfile.kved} | ${currentProfile.region}</td></tr>
                <tr><td style="border: 1px solid #cbd5e1; padding: 6px; font-weight: bold; background: #f8fafc;">Масштаб та Власний внесок</td><td style="border: 1px solid #cbd5e1; padding: 6px;">${currentProfile.size_category} | Співфінансування: ${currentProfile.own_contribution_percent}</td></tr>
                <tr><td style="border: 1px solid #cbd5e1; padding: 6px; font-weight: bold; background: #f8fafc;">Інвестиційний фокус</td><td style="border: 1px solid #cbd5e1; padding: 6px;">${currentProfile.investment_focus}</td></tr>
            </table>
            <h3 style="font-size: 13.5px; color: #059669;">2. Рекомендовані грантові програми за результатами скорингу</h3>
            ${currentScoredGrants.map(g => `
                <div style="border: 1px solid #cbd5e1; padding: 8px 10px; border-radius: 6px; margin-bottom: 8px; font-size: 11.5px;">
                    <strong>${g.title} — Відповідність ${g.score}%</strong><br>
                    Донор: ${g.donor} | Обсяг фінансування: ${g.max_amount} (Внесок від ${g.min_own}%)
                </div>
            `).join('')}
        `;

		wrapper.style.display = 'flex';
		window.scrollTo(0, 0);
		await new Promise(r => setTimeout(r, 150));

		try {
			await html2pdf().set({
				margin: [10, 10, 10, 10],
				filename: 'AgroGrant_Analytical_Report.pdf',
				image: { type: 'jpeg', quality: 0.98 },
				html2canvas: { scale: 2, useCORS: true, backgroundColor: '#ffffff', scrollY: 0, scrollX: 0 },
				jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' }
			}).from(target).save();
		} finally {
			wrapper.style.display = 'none';
			target.innerHTML = '';
			window.scrollTo(0, prevY);
			btn.disabled = false;
			btn.textContent = orig;
		}
	});

	document.getElementById('downloadDocxBtn').addEventListener('click', () => {
		logAction('DOCX_REPORT_EXPORT', `EDRPOU: ${currentProfile.edrpou}`);
		const params = new URLSearchParams({
			edrpou: currentProfile.edrpou,
			company: currentProfile.company_name
		});
		window.open(`${BACKEND_URL}/export/00000000-0000-0000-0000-000000000000?${params.toString()}`, '_blank');
	});
});
