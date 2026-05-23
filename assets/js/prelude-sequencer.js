const scenes = document.querySelectorAll('.scene');
const bar = document.getElementById('progress-bar');
let current = 0;

const config = [
    { dur: 6000 }, // Ouverture
    { dur: 8000 }, // The Object
    { dur: 8000 }, // The Gap
    { dur: null }  // Portal
];

function next() {
    if (current >= scenes.length - 1) return;
    goTo(current + 1);
}

function goTo(index) {
    scenes[current].classList.remove('active');
    current = index;
    scenes[current].classList.add('active');

    const d = config[current].dur;
    if (d) {
        bar.style.transition = 'none';
        bar.style.width = '0%';
        setTimeout(() => {
            bar.style.transition = `width ${d}ms linear`;
            bar.style.width = '100%';
        }, 50);
        setTimeout(next, d);
    } else {
        bar.style.width = '0%';
    }
}

// 绑定入口：点击世界卡片带参数跳转
document.querySelectorAll('.w-panel').forEach(p => {
    p.addEventListener('click', () => {
        const world = p.dataset.world;
        window.location.href = `initial.html?world=${world}`;
    });
});

document.getElementById('skip-btn').addEventListener('click', () => goTo(3));

// 启动
goTo(0);