const bg = document.getElementById('bg');
const bx = bg.getContext('2d');
let stars = [];

function init() {
    bg.width = window.innerWidth;
    bg.height = window.innerHeight;
    stars = Array.from({length: 1200}, () => ({
        x: Math.random() * bg.width,
        y: Math.random() * bg.height,
        r: Math.random() * 1.5,
        a: Math.random() * 0.8
    }));
}

function draw() {
    bx.fillStyle = '#020205';
    bx.fillRect(0, 0, bg.width, bg.height);

    // 渲染星云氛围
    const grd = bx.createRadialGradient(bg.width/2, bg.height/2, 0, bg.width/2, bg.height/2, bg.width/2);
    grd.addColorStop(0, 'rgba(200, 160, 100, 0.05)');
    grd.addColorStop(1, 'transparent');
    bx.fillStyle = grd;
    bx.fillRect(0, 0, bg.width, bg.height);

    // 渲染繁星
    stars.forEach(s => {
        bx.globalAlpha = s.a;
        bx.fillStyle = '#fff';
        bx.beginPath();
        bx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        bx.fill();
    });
    bx.globalAlpha = 1;
    requestAnimationFrame(draw);
}

window.addEventListener('resize', init);
init();
draw();