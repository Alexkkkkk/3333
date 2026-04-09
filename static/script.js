// --- CONFIGURATION ---
const QC_CONTRACT = "EQBrZYrk2PA659JmMCnkWVbLp14-5Gq8Yp9X_H9uR1pI_6_P"; 
const QC_SYMBOL = "QC";
const QC_IMAGE = "https://tonraffles.app/jetton/logo.png";

const tonConnectUI = new TON_CONNECT_UI.TonConnectUI({
    manifestUrl: 'https://quantum.bothost.tech/static/tonconnect-manifest.json',
    buttonRootId: 'connectBtn'
});

let userWallet = null;

// --- TONCONNECT HANDLERS ---
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

async function syncWalletWithBackend(address) {
    try {
        await fetch('/api/connect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ address, timestamp: Date.now() })
        });
    } catch (e) { console.warn("Backend Sync Offline"); }
}

async function fetchWalletData(address) {
    try {
        const elements = {
            shortAddr: document.getElementById('wallet-short-addr'),
            profile: document.getElementById('user-profile-mini'),
            status: document.getElementById('profile-status'),
            mainBal: document.getElementById('main-balance-ton')
        };

        if(elements.shortAddr) elements.shortAddr.innerText = `${address.slice(0, 4)}...${address.slice(-4)}`;
        if(elements.profile) elements.profile.classList.remove('hidden');
        if(elements.status) elements.status.innerText = "VERIFIED OPERATOR";

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

function renderJettons(balances, tonBalance) {
    const list = document.getElementById('tokenList');
    if (!list) return;
    list.innerHTML = '';
    
    // 1. Render TON
    list.innerHTML += createTokenRow("TON", "TON", tonBalance, "https://ton.org/download/ton_symbol.png", "5.24", false);

    // 2. Render QC (Core Asset)
    const qcAsset = balances.find(b => b.jetton.address === QC_CONTRACT);
    if(qcAsset) {
        const j = qcAsset.jetton;
        const bal = (parseInt(qcAsset.balance) / Math.pow(10, j.decimals)).toFixed(2);
        list.insertAdjacentHTML('afterbegin', createTokenRow(j.name, j.symbol, bal, j.image || QC_IMAGE, "0.00", true));
    }

    // 3. Other Jettons
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
    const highlight = isQC ? 'border border-cyan-500/40 bg-cyan-500/10' : 'hover:bg-white/5';
    const badge = isQC ? '<span class="text-[8px] bg-cyan-500 text-black px-1 rounded ml-1 font-black">CORE</span>' : '';
    const usdValue = (balance * price).toFixed(2);

    return `
        <div class="flex justify-between items-center px-3 py-2 rounded-xl transition-all ${highlight} mb-1 border border-transparent">
            <div class="flex items-center gap-3">
                <img src="${img}" class="w-8 h-8 rounded-full border border-white/10" onerror="this.src='https://wallet.tg/assets/logo.png'">
                <div>
                    <p class="font-bold text-sm text-white">${symbol}${badge}</p>
                    <p class="text-[9px] text-slate-500">${name}</p>
                </div>
            </div>
            <div class="text-right">
                <p class="font-bold text-sm text-white">${balance}</p>
                <p class="text-[9px] text-emerald-400 font-mono">${isQC ? 'STABLE' : '$' + usdValue}</p>
            </div>
        </div>
    `;
}

// --- SWAP LOGIC ---
function calculateSwap() {
    const input = document.getElementById('swapInput');
    const output = document.getElementById('swapOutput');
    const rate = 1000;
    if(input && output) output.value = input.value ? (input.value * rate).toFixed(0) : '';
}

async function executeSwap() {
    if (!userWallet) { await tonConnectUI.connectWallet(); return; }
    const amount = document.getElementById('swapInput')?.value;
    if(!amount || amount <= 0) return showWhaleAlert("Error", "Enter TON amount");

    const transaction = {
        validUntil: Math.floor(Date.now() / 1000) + 300,
        messages: [{
            address: "EQB3ncyBUTjZUA5EnGhc_f_697L6SSc88_m5_N0D83v97m8",
            amount: (amount * 1e9).toString(), 
        }]
    };

    try {
        await tonConnectUI.sendTransaction(transaction);
        showWhaleAlert("Order Sent", `Buying ${QC_SYMBOL}...`);
    } catch (e) { showWhaleAlert("Declined", "User rejected swap"); }
}

async function deployJetton() {
    if (!userWallet) { await tonConnectUI.connectWallet(); return; }
    const btn = document.getElementById('deployBtn');
    if(btn) { btn.innerText = "FORGING..."; btn.disabled = true; }
    
    const transaction = {
        validUntil: Math.floor(Date.now() / 1000) + 300,
        messages: [{
            address: "EQB3ncyBUTjZUA5EnGhc_f_697L6SSc88_m5_N0D83v97m8", 
            amount: "270000000",
        }]
    };

    try {
        await tonConnectUI.sendTransaction(transaction);
        showWhaleAlert("Success", "Contract modification initiated");
    } catch (e) { showWhaleAlert("Failed", "Transaction cancelled"); }
    finally { if(btn) { btn.disabled = false; btn.innerText = "Mint Jetton"; } }
}

// --- UI MANAGEMENT ---
function switchTab(tabId, el) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.getElementById(tabId)?.classList.add('active');
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    el.classList.add('active');
    if (tabId === 'analytics') setTimeout(initChart, 100);
}

function updateUIState() {
    const btns = { swap: document.getElementById('mainSwapBtn'), deploy: document.getElementById('deployBtn') };
    if(btns.swap) btns.swap.innerText = userWallet ? "Execute Swap" : "Connect Wallet";
    if(btns.deploy) btns.deploy.innerText = userWallet ? "Mint Jetton" : "Connect Wallet";
}

function resetWalletData() {
    document.getElementById('user-profile-mini')?.classList.add('hidden');
    const list = document.getElementById('tokenList');
    if(list) list.innerHTML = '<p class="text-center text-slate-500 py-10 text-[10px]">AUTH REQUIRED</p>';
    updateUIState();
}

function showWhaleAlert(title, text) {
    const container = document.getElementById('whale-alerts');
    const alert = document.createElement('div');
    alert.className = 'whale-toast';
    alert.innerHTML = `<p class="text-cyan-400 font-bold text-[10px] uppercase">${title}</p><p class="text-white text-[10px] opacity-80">${text}</p>`;
    container.appendChild(alert);
    setTimeout(() => { alert.style.opacity = '0'; setTimeout(() => alert.remove(), 500); }, 4000);
}

// --- VISUAL EFFECTS ---
let myChart = null;
function initChart() {
    const ctx = document.getElementById('liquidityChart')?.getContext('2d');
    if(!ctx) return;
    if(myChart) myChart.destroy();
    myChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: ['12:00', '13:00', '14:00', '15:00', '16:00', '17:00'],
            datasets: [{
                data: [980, 1050, 1020, 1100, 1080, 1250],
                borderColor: '#00f2ff',
                backgroundColor: 'rgba(0, 242, 255, 0.05)',
                fill: true, tension: 0.4, borderWidth: 2, pointRadius: 0
            }]
        },
        options: { 
            responsive: true, 
            maintainAspectRatio: false, 
            plugins: { legend: { display: false } }, 
            scales: { 
                y: { grid: { color: 'rgba(255,255,255,0.02)' }, ticks: { color: '#475569', size: 9 } }, 
                x: { grid: { display: false }, ticks: { color: '#475569', size: 9 } } 
            } 
        }
    });
}

// Particle Engine
const canvasBg = document.getElementById('bg-canvas');
if(canvasBg) {
    const ctx = canvasBg.getContext('2d');
    let pts = [];
    function init() {
        canvasBg.width = window.innerWidth; canvasBg.height = window.innerHeight;
        pts = Array.from({length: 45}, () => ({ 
            x: Math.random()*canvasBg.width, y: Math.random()*canvasBg.height, 
            s: Math.random()*1.2, v: Math.random()*0.2 + 0.05 
        }));
    }
    function draw() {
        ctx.clearRect(0,0,canvasBg.width, canvasBg.height);
        ctx.fillStyle = "rgba(0, 242, 255, 0.15)";
        pts.forEach(p => { 
            p.y -= p.v; 
            if(p.y < 0) p.y = canvasBg.height; 
            ctx.beginPath(); ctx.arc(p.x, p.y, p.s, 0, Math.PI*2); ctx.fill(); 
        });
        requestAnimationFrame(draw);
    }
    window.addEventListener('resize', init);
    init(); draw();
}
