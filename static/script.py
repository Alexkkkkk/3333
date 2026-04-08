// ==========================================================
// PROJECT: QUANTUM TERMINAL v4.1 ENGINE
// ROLE: FRONTEND LOGIC & BLOCKCHAIN INTERACTION
// CORE ASSET: QUANCORE (QC)
// ==========================================================

// Конфигурация активов
const QC_CONTRACT = "EQBrZYrk2PA659JmMCnkWVbLp14-5Gq8Yp9X_H9uR1pI_6_P"; // Адрес из скриншота
const QC_SYMBOL = "QC";

// Конфигурация TonConnect
const tonConnectUI = new TON_CONNECT_UI.TonConnectUI({
    manifestUrl: 'https://quantum.bothost.tech/static/tonconnect-manifest.json',
    buttonRootId: 'connectBtn'
});

let userWallet = null;

// --- СЛУШАТЕЛЬ СТАТУСА КОШЕЛЬКА ---
tonConnectUI.onStatusChange(async wallet => {
    userWallet = wallet;
    updateUIState();
    
    if(wallet) {
        const address = wallet.account.address;
        showWhaleAlert("Quantum Sync", "Operator Verified");
        syncWalletWithBackend(address);
        await fetchWalletData(address);
    } else {
        resetWalletData();
    }
});

/**
 * СИНХРОНИЗАЦИЯ С BACKEND
 */
async function syncWalletWithBackend(address) {
    try {
        await fetch('/api/connect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ address, timestamp: Date.now() })
        });
    } catch (e) { console.error("Backend Offline"); }
}

/**
 * ПОЛУЧЕНИЕ ДАННЫХ ИЗ БЛОКЧЕЙНА (TONAPI)
 */
async function fetchWalletData(address) {
    try {
        // UI Элементы
        const elements = {
            shortAddr: document.getElementById('wallet-short-addr'),
            profile: document.getElementById('user-profile-mini'),
            status: document.getElementById('profile-status'),
            fullAddr: document.getElementById('profile-full-address'),
            mainBal: document.getElementById('main-balance-ton')
        };

        if(elements.shortAddr) elements.shortAddr.innerText = `${address.slice(0, 4)}...${address.slice(-4)}`;
        if(elements.profile) elements.profile.classList.remove('hidden');
        if(elements.status) elements.status.innerText = "VERIFIED OPERATOR";
        if(elements.fullAddr) elements.fullAddr.innerText = address;

        // Загрузка данных аккаунта и жетонов
        const [accRes, jettonRes] = await Promise.all([
            fetch(`https://tonapi.io/v2/accounts/${address}`),
            fetch(`https://tonapi.io/v2/accounts/${address}/jettons`)
        ]);

        const accData = await accRes.json();
        const jettonData = await jettonRes.json();
        
        const tonBalance = (accData.balance / 1e9).toFixed(2);
        if(elements.mainBal) elements.mainBal.innerText = `${tonBalance} TON`;

        renderJettons(jettonData.balances, tonBalance);
    } catch (e) {
        showWhaleAlert("Sync Error", "Blockchain data unreachable");
    }
}

/**
 * РЕНДЕР СПИСКА ТОКЕНОВ (С ФИЛЬТРАЦИЕЙ QC)
 */
function renderJettons(balances, tonBalance) {
    const list = document.getElementById('tokenList');
    if (!list) return;
    list.innerHTML = '';
    
    // 1. Сначала TON
    list.innerHTML += createTokenRow("TON", "TON", tonBalance, "https://ton.org/download/ton_symbol.png", "5.24", false);

    // 2. Ищем QUANCORE (QC) среди балансов
    const qcAsset = balances.find(b => b.jetton.address === QC_CONTRACT);
    if(qcAsset) {
        const j = qcAsset.jetton;
        const bal = (parseInt(qcAsset.balance) / Math.pow(10, j.decimals)).toFixed(2);
        list.insertAdjacentHTML('afterbegin', createTokenRow(j.name, j.symbol, bal, j.image, "0.00", true));
    }

    // 3. Остальные токены
    balances.forEach(item => {
        if(item.jetton.address === QC_CONTRACT) return;
        const j = item.jetton;
        const bal = (parseInt(item.balance) / Math.pow(10, j.decimals)).toFixed(2);
        if (parseFloat(bal) > 0) {
            const price = item.price ? item.price.prices.USD : 0;
            list.innerHTML += createTokenRow(j.name, j.symbol, bal, j.image, price, false);
        }
    });
}

function createTokenRow(name, symbol, balance, img, price, isQC = false) {
    const highlight = isQC ? 'border border-cyan-500/30 bg-cyan-500/5 shadow-[0_0_15px_rgba(0,242,255,0.1)]' : 'hover:bg-white/5';
    const badge = isQC ? '<span class="text-[8px] bg-cyan-500 text-black px-1 rounded ml-1 font-black">CORE</span>' : '';
    const usdValue = (balance * price).toFixed(2);

    return `
        <div class="token-row flex justify-between items-center px-3 py-2 rounded-xl transition-all ${highlight} mb-1">
            <div class="flex items-center gap-3">
                <img src="${img}" class="w-8 h-8 rounded-full border border-white/10" onerror="this.src='https://wallet.tg/assets/logo.png'">
                <div>
                    <p class="font-bold text-sm text-white">${symbol}${badge}</p>
                    <p class="text-[10px] text-slate-500">${name}</p>
                </div>
            </div>
            <div class="text-right">
                <p class="font-bold text-sm text-white">${balance}</p>
                <p class="text-[9px] text-emerald-400 font-mono">${isQC ? 'STABLE' : '$' + usdValue}</p>
            </div>
        </div>
    `;
}

/**
 * ЛОГИКА ОБМЕНА (SWAP) НА QC
 */
function calculateSwap() {
    const input = document.getElementById('swapInput');
    const output = document.getElementById('swapOutput');
    if(!input || !output) return;
    
    // Фиксированный курс терминала для QC (например 1 TON = 1000 QC)
    const rate = 1000;
    output.value = input.value ? (input.value * rate).toFixed(0) : '';
}

async function executeSwap() {
    if (!userWallet) { await tonConnectUI.connectWallet(); return; }
    const amount = document.getElementById('swapInput')?.value;
    if(!amount || amount <= 0) return showWhaleAlert("Error", "Enter TON amount");

    const transaction = {
        validUntil: Math.floor(Date.now() / 1000) + 300,
        messages: [{
            address: "EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c", // Кошелек сбора ликвидности
            amount: (amount * 1e9).toString(), 
        }]
    };

    try {
        await tonConnectUI.sendTransaction(transaction);
        showWhaleAlert("Order Sent", `Swapping TON for ${QC_SYMBOL}`);
    } catch (e) { showWhaleAlert("Declined", "User rejected swap"); }
}

/**
 * ФУНКЦИИ ИНТЕРФЕЙСА
 */
function switchTab(tabId, el) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.getElementById(tabId)?.classList.add('active');
    if (el) {
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        el.classList.add('active');
    }
    if (tabId === 'analytics') setTimeout(initChart, 100);
}

function updateUIState() {
    const btns = ['mainSwapBtn', 'deployBtn'];
    btns.forEach(id => {
        const btn = document.getElementById(id);
        if(btn) btn.innerText = userWallet ? (id === 'deployBtn' ? "Mint Jetton" : "Execute Swap") : "Connect Wallet";
    });
}

function showWhaleAlert(title, text) {
    const container = document.getElementById('whale-alerts');
    if(!container) return;
    const alert = document.createElement('div');
    alert.className = 'whale-toast';
    alert.innerHTML = `
        <div class="flex flex-col">
            <p class="text-cyan-400 font-bold text-xs uppercase">${title}</p>
            <p class="text-white text-[10px] opacity-80">${text}</p>
        </div>
    `;
    container.appendChild(alert);
    setTimeout(() => {
        alert.style.opacity = '0';
        setTimeout(() => alert.remove(), 500);
    }, 4000);
}

// ПАРАЛЛАКС И ЧАСТИЦЫ
document.addEventListener('mousemove', (e) => {
    const x = (e.clientX / window.innerWidth) * 20;
    const y = (e.clientY / window.innerHeight) * 20;
    document.body.style.backgroundPosition = `${x}% ${y}%`;
});

const canvasBg = document.getElementById('bg-canvas');
if(canvasBg) {
    const ctx = canvasBg.getContext('2d');
    let pts = [];
    function init() {
        canvasBg.width = window.innerWidth; canvasBg.height = window.innerHeight;
        pts = Array.from({length: 40}, () => ({ 
            x: Math.random()*canvasBg.width, y: Math.random()*canvasBg.height, 
            s: Math.random()*1.5, v: Math.random()*0.2 + 0.1 
        }));
    }
    function draw() {
        ctx.clearRect(0,0,canvasBg.width, canvasBg.height);
        ctx.fillStyle = "rgba(0, 242, 255, 0.2)";
        pts.forEach(p => { 
            p.y -= p.v; if(p.y < 0) p.y = canvasBg.height; 
            ctx.beginPath(); ctx.arc(p.x, p.y, p.s, 0, Math.PI*2); ctx.fill(); 
        });
        requestAnimationFrame(draw);
    }
    window.addEventListener('resize', init);
    init(); draw();
}
