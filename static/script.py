// ==========================================================
// PROJECT: QUANTUM TERMINAL v4.1 ENGINE
// ROLE: FRONTEND LOGIC & BLOCKCHAIN INTERACTION
// ==========================================================

// --- КОНФИГУРАЦИЯ TONCONNECT ---
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
        showWhaleAlert("Wallet Synced", "Quantum Terminal Ready");
        
        // Автоматическая синхронизация с вашим main.py
        syncWalletWithBackend(address);
        
        await fetchWalletData(address);
    } else {
        resetWalletData();
    }
});

/**
 * СИНХРОНИЗАЦИЯ С BACKEND (Quantum V3 Core)
 */
async function syncWalletWithBackend(address) {
    try {
        const response = await fetch('/api/connect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                address: address,
                timestamp: Date.now()
            })
        });
        const result = await response.json();
        console.log("Quantum Backend Sync:", result.status);
    } catch (e) {
        console.error("Quantum Backend Sync: Offline", e);
    }
}

/**
 * ПОЛУЧЕНИЕ ДАННЫХ ЧЕРЕЗ TONAPI
 */
async function fetchWalletData(address) {
    try {
        const shortAddr = `${address.slice(0, 4)}...${address.slice(-4)}`;
        const walletDisplay = document.getElementById('wallet-short-addr');
        if(walletDisplay) walletDisplay.innerText = shortAddr;
        
        const profileMini = document.getElementById('user-profile-mini');
        if(profileMini) profileMini.classList.remove('hidden');

        const profileStatus = document.getElementById('profile-status');
        if(profileStatus) profileStatus.innerText = "VERIFIED OPERATOR";
        
        const fullAddrDisp = document.getElementById('profile-full-address');
        if(fullAddrDisp) fullAddrDisp.innerText = address;
        
        const walletInfo = document.getElementById('profile-wallet-info');
        const connectPrompt = document.getElementById('profile-connect-prompt');
        if(walletInfo) walletInfo.classList.remove('hidden');
        if(connectPrompt) connectPrompt.classList.add('hidden');

        // Загрузка баланса TON и Жетонов
        const [accRes, jettonRes] = await Promise.all([
            fetch(`https://tonapi.io/v2/accounts/${address}`),
            fetch(`https://tonapi.io/v2/accounts/${address}/jettons`)
        ]);

        const accData = await accRes.json();
        const jettonData = await jettonRes.json();
        
        const tonBalance = (accData.balance / 1e9).toFixed(2);
        const mainBal = document.getElementById('main-balance-ton');
        if(mainBal) mainBal.innerText = `${tonBalance} TON`;

        renderJettons(jettonData.balances, tonBalance);
    } catch (e) {
        console.error("Quantum Sync Error:", e);
        showWhaleAlert("Data Error", "Failed to sync assets");
    }
}

/**
 * РЕНДЕР СПИСКА ТОКЕНОВ
 */
function renderJettons(balances, tonBalance) {
    const list = document.getElementById('tokenList');
    if (!list) return;
    
    list.innerHTML = '';
    // Добавляем системный TON
    list.innerHTML += createTokenRow("TON", "TON", tonBalance, "https://ton.org/download/ton_symbol.png", "5.24");

    balances.forEach(item => {
        const j = item.jetton;
        const bal = (parseInt(item.balance) / Math.pow(10, j.decimals)).toFixed(2);
        if (parseFloat(bal) > 0) {
            const price = item.price ? item.price.prices.USD : 0;
            list.innerHTML += createTokenRow(j.name, j.symbol, bal, j.image, price);
        }
    });
}

function createTokenRow(name, symbol, balance, img, price) {
    const usdValue = price ? (balance * price).toFixed(2) : "0.00";
    return `
        <div class="token-row flex justify-between items-center px-3 py-2 hover:bg-white/5 rounded-xl transition-all">
            <div class="flex items-center gap-3">
                <img src="${img}" class="w-8 h-8 rounded-full border border-white/10" onerror="this.src='https://wallet.tg/assets/logo.png'">
                <div>
                    <p class="font-bold text-sm text-white">${symbol}</p>
                    <p class="text-[10px] text-slate-500">${name}</p>
                </div>
            </div>
            <div class="text-right">
                <p class="font-bold text-sm text-white">${balance}</p>
                <p class="text-[9px] text-emerald-400">$${usdValue}</p>
            </div>
        </div>
    `;
}

/**
 * ЛОГИКА ОБМЕНА (SWAP)
 */
function calculateSwap() {
    const input = document.getElementById('swapInput');
    const output = document.getElementById('swapOutput');
    if(!input || !output) return;
    
    const val = input.value;
    output.value = val ? (val * 450.25).toFixed(2) : ''; // Примерный курс QUAN
}

async function executeSwap() {
    if (!userWallet) { await tonConnectUI.connectWallet(); return; }
    
    const amount = document.getElementById('swapInput')?.value;
    if(!amount || amount <= 0) {
        showWhaleAlert("Input Required", "Enter TON amount");
        return;
    }

    const transaction = {
        validUntil: Math.floor(Date.now() / 1000) + 300,
        messages: [{
            address: "EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c", // ZERO ADDRESS или ваш кошелек
            amount: (amount * 1e9).toString(), 
        }]
    };

    try {
        await tonConnectUI.sendTransaction(transaction);
        showWhaleAlert("Swap Initiated", `${amount} TON -> QUAN`);
    } catch (e) {
        showWhaleAlert("Cancelled", "Transaction rejected");
    }
}

/**
 * УПРАВЛЕНИЕ ТРАНЗАКЦИЯМИ (MINT / DEPLOY)
 */
async function deployJetton() {
    if (!userWallet) { await tonConnectUI.connectWallet(); return; }
    
    const name = document.getElementById('jettonName')?.value;
    const symbol = document.getElementById('jettonSymbol')?.value;
    const supply = document.getElementById('jettonSupply')?.value;

    if(!name || !symbol || !supply) {
        showWhaleAlert("System Error", "Fill all deployment fields");
        return;
    }

    const btn = document.getElementById('deployBtn');
    if(btn) {
        btn.innerText = "FORGING...";
        btn.disabled = true;
    }

    const transaction = {
        validUntil: Math.floor(Date.now() / 1000) + 300,
        messages: [{
            address: "EQB3ncyBUTjZUA5EnGhc_f_697L6SSc88_m5_N0D83v97m8", 
            amount: "270000000", // 0.27 TON fee
        }]
    };

    try {
        await tonConnectUI.sendTransaction(transaction);
        showWhaleAlert("Mint Success", `${symbol} deployment broadcasted`);
    } catch (e) {
        showWhaleAlert("Mint Failed", "Transaction rejected");
    } finally {
        if(btn) {
            btn.disabled = false;
            btn.innerText = "Mint Jetton";
        }
    }
}

/**
 * СИСТЕМА ВКЛАДОК
 */
function switchTab(tabId, el) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    const activeTab = document.getElementById(tabId);
    if(activeTab) activeTab.classList.add('active');
    
    if (el) {
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        el.classList.add('active');
    }
    
    if (tabId === 'analytics') setTimeout(initChart, 100);
}

/**
 * ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ИНТЕРФЕЙСА
 */
function resetWalletData() {
    const profileMini = document.getElementById('user-profile-mini');
    if(profileMini) profileMini.classList.add('hidden');
    
    const mainBal = document.getElementById('main-balance-ton');
    if(mainBal) mainBal.innerText = "0.00 TON";
    
    const list = document.getElementById('tokenList');
    if(list) list.innerHTML = '<p class="text-center text-slate-500 py-10 text-xs">Подключите кошелек</p>';
    
    const pStatus = document.getElementById('profile-status');
    if(pStatus) pStatus.innerText = "GUEST OPERATOR";
    
    document.getElementById('profile-wallet-info')?.classList.add('hidden');
    document.getElementById('profile-connect-prompt')?.classList.remove('hidden');
    updateUIState();
}

function updateUIState() {
    const swapBtn = document.getElementById('mainSwapBtn');
    const deployBtn = document.getElementById('deployBtn');
    
    if(swapBtn) swapBtn.innerText = userWallet ? "Execute Swap" : "Connect Wallet";
    if(deployBtn) deployBtn.innerText = userWallet ? "Mint Jetton" : "Connect Wallet";
}

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

// ПАРАЛЛАКС ФОНА
function handleMouseMove(e) {
    const x = (e.clientX / window.innerWidth) * 20;
    const y = (e.clientY / window.innerHeight) * 20;
    document.body.style.backgroundPosition = `${x}% ${y}%`;
}
document.addEventListener('mousemove', handleMouseMove);

// ГРАФИК (Chart.js)
let myQuantumChart = null;
function initChart() {
    const canvas = document.getElementById('liquidityChart');
    if(!canvas) return;
    const ctx = canvas.getContext('2d');
    if(myQuantumChart) myQuantumChart.destroy();
    
    myQuantumChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00'],
            datasets: [{
                data: [450, 520, 490, 610, 580, 720],
                borderColor: '#00f2ff',
                backgroundColor: 'rgba(0, 242, 255, 0.05)',
                fill: true, tension: 0.4, borderWidth: 2, pointRadius: 0
            }]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { grid: { color: 'rgba(255,255,255,0.03)' }, ticks: { color: '#475569', size: 10 } },
                x: { grid: { display: false }, ticks: { color: '#475569', size: 10 } }
            }
        }
    });
}

// ИНИЦИАЛИЗАЦИЯ ЧАСТИЦ (Background)
const canvasBg = document.getElementById('bg-canvas');
if(canvasBg) {
    const ctxP = canvasBg.getContext('2d');
    let pts = [];
    function initCanvas() {
        canvasBg.width = window.innerWidth; canvasBg.height = window.innerHeight;
        pts = Array.from({length: 40}, () => ({ 
            x: Math.random()*canvasBg.width, y: Math.random()*canvasBg.height, 
            s: Math.random()*1.5 + 0.5, v: Math.random()*0.3 + 0.1 
        }));
    }
    function draw() {
        ctxP.clearRect(0,0,canvasBg.width, canvasBg.height);
        ctxP.fillStyle = "rgba(0, 242, 255, 0.3)";
        pts.forEach(p => { 
            p.y -= p.v; if(p.y < 0) p.y = canvasBg.height; 
            ctxP.beginPath(); ctxP.arc(p.x, p.y, p.s, 0, Math.PI*2); ctxP.fill(); 
        });
        requestAnimationFrame(draw);
    }
    window.addEventListener('resize', initCanvas);
    initCanvas(); draw();
}
