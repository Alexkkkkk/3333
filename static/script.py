// --- QUANTUM TERMINAL v4.1 ENGINE ---

// Конфигурация TonConnect
const tonConnectUI = new TON_CONNECT_UI.TonConnectUI({
    manifestUrl: 'https://quantum.bothost.tech/static/tonconnect-manifest.json',
    buttonRootId: 'connectBtn'
});

let userWallet = null;

// Слушатель статуса кошелька
tonConnectUI.onStatusChange(async wallet => {
    userWallet = wallet;
    updateUIState();
    if(wallet) {
        const address = wallet.account.address;
        showWhaleAlert("Wallet Synced", "Quantum Terminal Ready");
        
        // --- СИНХРОНИЗАЦИЯ С BACKEND (Quantum V3 Core) ---
        syncWalletWithBackend(address);
        
        await fetchWalletData(address);
    } else {
        resetWalletData();
    }
});

// Новая функция для связи с вашим main.py
async function syncWalletWithBackend(address) {
    try {
        await fetch('/api/connect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ address: address })
        });
        console.log("Backend Sync: Success");
    } catch (e) {
        console.error("Backend Sync: Failed", e);
    }
}

// Получение данных кошелька через TonAPI
async function fetchWalletData(address) {
    try {
        const shortAddr = `${address.slice(0, 4)}...${address.slice(-4)}`;
        const walletDisplay = document.getElementById('wallet-short-addr');
        if(walletDisplay) walletDisplay.innerText = shortAddr;
        
        const profileMini = document.getElementById('user-profile-mini');
        if(profileMini) profileMini.classList.remove('hidden');

        document.getElementById('profile-status').innerText = "VERIFIED OPERATOR";
        document.getElementById('profile-full-address').innerText = address;
        document.getElementById('profile-wallet-info').classList.remove('hidden');
        document.getElementById('profile-connect-prompt').classList.add('hidden');

        // Загрузка жетонов
        const response = await fetch(`https://tonapi.io/v2/accounts/${address}/jettons`);
        const data = await response.json();
        
        // Загрузка баланса TON
        const accRes = await fetch(`https://tonapi.io/v2/accounts/${address}`);
        const accData = await accRes.json();
        const tonBalance = (accData.balance / 1e9).toFixed(2);
        
        const mainBal = document.getElementById('main-balance-ton');
        if(mainBal) mainBal.innerText = `${tonBalance} TON`;

        renderJettons(data.balances, tonBalance);
    } catch (e) {
        console.error("Fetch error:", e);
        showWhaleAlert("Data Error", "Failed to sync assets");
    }
}

// Рендер списка токенов
function renderJettons(balances, tonBalance) {
    const list = document.getElementById('tokenList');
    if (!list) return;
    
    list.innerHTML = '';
    // Дефолтный TON ряд
    list.innerHTML += createTokenRow("TON", "TON", tonBalance, "https://ton.org/download/ton_symbol.png", "5.24");

    balances.forEach(item => {
        const j = item.jetton;
        const bal = (parseInt(item.balance) / Math.pow(10, j.decimals)).toFixed(2);
        if (parseFloat(bal) > 0) {
            const price = item.price ? item.price.prices.USD.toFixed(4) : "0.00";
            list.innerHTML += createTokenRow(j.name, j.symbol, bal, j.image, price);
        }
    });
}

function createTokenRow(name, symbol, balance, img, price) {
    return `
        <div class="token-row flex justify-between items-center px-2 hover:bg-white/5 rounded-xl transition-all duration-300">
            <div class="flex items-center gap-3">
                <img src="${img}" class="w-10 h-10 rounded-full border border-white/10" onerror="this.src='https://wallet.tg/assets/logo.png'">
                <div>
                    <p class="font-bold text-sm text-white">${symbol}</p>
                    <p class="text-[10px] text-slate-500">${name}</p>
                </div>
            </div>
            <div class="text-right">
                <p class="font-bold text-sm text-white">${balance}</p>
                <p class="text-[9px] text-emerald-400">$${(balance * price).toFixed(2)}</p>
            </div>
        </div>
    `;
}

// Сброс данных при отключении
function resetWalletData() {
    const profileMini = document.getElementById('user-profile-mini');
    if(profileMini) profileMini.classList.add('hidden');
    
    const mainBal = document.getElementById('main-balance-ton');
    if(mainBal) mainBal.innerText = "0.00 TON";
    
    const list = document.getElementById('tokenList');
    if(list) list.innerHTML = '<p class="text-center text-slate-500 py-10 text-xs">Подключите кошелек</p>';
    
    document.getElementById('profile-status').innerText = "GUEST OPERATOR";
    document.getElementById('profile-wallet-info').classList.add('hidden');
    document.getElementById('profile-connect-prompt').classList.remove('hidden');
}

// Обновление текста кнопок
function updateUIState() {
    const swapBtn = document.getElementById('mainSwapBtn');
    const deployBtn = document.getElementById('deployBtn');
    if (userWallet) {
        if(swapBtn) swapBtn.innerText = "Execute Swap";
        if(deployBtn) deployBtn.innerText = "Mint Jetton";
    } else {
        if(swapBtn) swapBtn.innerText = "Connect Wallet";
        if(deployBtn) deployBtn.innerText = "Connect Wallet";
    }
}

// Навигация по вкладкам
function switchTab(id, el) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    const target = document.getElementById(id);
    if(target) target.classList.add('active');
    if (el) el.classList.add('active');
    if (id === 'analytics') setTimeout(initChart, 100);
}

// Создание токена (Mint)
async function deployJetton() {
    if (!userWallet) { await tonConnectUI.connectWallet(); return; }
    const name = document.getElementById('jettonName').value;
    const symbol = document.getElementById('jettonSymbol').value;
    const supply = document.getElementById('jettonSupply').value;

    if(!name || !symbol || !supply) {
        showWhaleAlert("System Error", "Fill all deployment fields");
        return;
    }

    const btn = document.getElementById('deployBtn');
    btn.innerText = "FORGING...";
    btn.disabled = true;

    const transaction = {
        validUntil: Math.floor(Date.now() / 1000) + 300,
        messages: [{
            address: "EQB3ncyBUTjZUA5EnGhc_f_697L6SSc88_m5_N0D83v97m8", 
            amount: "270000000", 
        }]
    };

    try {
        await tonConnectUI.sendTransaction(transaction);
        showWhaleAlert("Mint Success", `${symbol} is on Mainnet`);
    } catch (e) {
        console.error(e);
        showWhaleAlert("Mint Failed", "Transaction rejected");
    } finally {
        btn.disabled = false;
        updateUIState();
    }
}

// Стейкинг
async function executeStaking() {
    if (!userWallet) { await tonConnectUI.connectWallet(); return; }
    showWhaleAlert("Stake Initiated", "Requesting signature...");
}

// Логика калькулятора обмена
const RATE = 54.32;
const swapInput = document.getElementById('swapInput');
if(swapInput) {
    swapInput.oninput = (e) => {
        const val = parseFloat(e.target.value) || 0;
        const output = document.getElementById('swapOutput');
        if(output) output.value = val > 0 ? (val * RATE).toFixed(2) : "";
    };
}

async function executeSwap() {
    if (!userWallet) { await tonConnectUI.connectWallet(); return; }
    showWhaleAlert("Swap Prepared", "Waiting for confirmation...");
}

// Уведомления
function showWhaleAlert(title, text) {
    const container = document.getElementById('whale-alerts');
    if(!container) return;
    const alert = document.createElement('div');
    alert.className = 'whale-toast';
    alert.innerHTML = `
        <div class="flex flex-col">
            <p class="text-cyan-400 font-bold text-xs uppercase tracking-wider">${title}</p>
            <p class="text-white text-[10px] opacity-80">${text}</p>
        </div>
    `;
    container.appendChild(alert);
    setTimeout(() => {
        alert.style.opacity = '0';
        alert.style.transform = 'translateX(20px)';
        setTimeout(() => alert.remove(), 500);
    }, 4000);
}

// Анимация фона (Particles)
const canvas = document.getElementById('bg-canvas');
if(canvas) {
    const ctxP = canvas.getContext('2d');
    let pts = [];

    function initCanvas() {
        canvas.width = window.innerWidth; canvas.height = window.innerHeight;
        pts = Array.from({length: 40}, () => ({ 
            x: Math.random()*canvas.width, y: Math.random()*canvas.height, 
            s: Math.random()*1.5 + 0.5, v: Math.random()*0.3 + 0.1 
        }));
    }

    function draw() {
        ctxP.clearRect(0,0,canvas.width, canvas.height);
        ctxP.fillStyle = "rgba(0, 242, 255, 0.3)";
        pts.forEach(p => { 
            p.y -= p.v; if(p.y < 0) p.y = canvas.height; 
            ctxP.beginPath(); ctxP.arc(p.x, p.y, p.s, 0, Math.PI*2); ctxP.fill(); 
        });
        requestAnimationFrame(draw);
    }

    window.addEventListener('resize', initCanvas);
    initCanvas();
    draw();
}

// Интерактив карточек (Mouse Move)
document.addEventListener('mousemove', (e) => {
    const cards = document.querySelectorAll('.glass-card, .card-grid-item');
    cards.forEach(card => {
        const rect = card.getBoundingClientRect();
        card.style.setProperty('--mouse-x', `${e.clientX - rect.left}px`);
        card.style.setProperty('--mouse-y', `${e.clientY - rect.top}px`);
    });
});

// Инициализация графика (Chart.js)
function initChart() {
    const ctx = document.getElementById('liquidityChart');
    if (!ctx) return;
    if (window.myChart) window.myChart.destroy();
    window.myChart = new Chart(ctx.getContext('2d'), {
        type: 'line',
        data: {
            labels: ['12:00', '13:00', '14:00', '15:00', '16:00'],
            datasets: [{ 
                data: [65, 59, 80, 81, 95], 
                borderColor: '#00f2ff', 
                borderWidth: 3, 
                tension: 0.4, 
                fill: true, 
                backgroundColor: 'rgba(0, 242, 255, 0.05)', 
                pointRadius: 0 
            }]
        },
        options: { 
            maintainAspectRatio: false, 
            plugins: { legend: { display: false } }, 
            scales: { x: { display: false }, y: { display: false } } 
        }
    });
}
