/**
 * Sistema de Notificações In-App - Barbearia do Thales
 * 
 * Funcionalidades:
 * - Polling a cada 3 segundos para verificar novas notificações
 * - Badge vermelho com contador no sino 🔔
 * - Animação pulsante quando chega notificação nova
 * - Som de notificação (com opção de mutar)
 * - Dropdown com lista de notificações
 * - Redirecionamento inteligente ao clicar
 */

// Configurações
const CONFIG = {
    INTERVALO_POLLING: 3000, // 3 segundos
    MAX_NOTIFICACOES_DROPDOWN: 10,
    DURACAO_ANIMACAO: 2000, // 2 segundos
};

// Estado global
let ultimoIdNotificacao = 0;
let audioContext = null;
let somMutado = false;
let intervalId = null;

// Inicialização
document.addEventListener('DOMContentLoaded', function() {
    console.log('🔔 Sistema de Notificações Inicializado');
    
    // Carregar preferência de som do localStorage
    somMutado = localStorage.getItem('notificacao_som_mutado') === 'true';
    atualizarBotaoSom();
    
    // Inicializar Web Audio API
    try {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
    } catch (e) {
        console.warn('⚠️ Web Audio API não suportada');
    }
    
    // Iniciar polling
    iniciarPolling();
    
    // Configurar event listeners
    configurarEventListeners();
});

/**
 * Inicia o polling para verificar novas notificações
 */
function iniciarPolling() {
    // Verificar imediatamente
    verificarNovasNotificacoes();
    
    // Depois verificar periodicamente
    intervalId = setInterval(verificarNovasNotificacoes, CONFIG.INTERVALO_POLLING);
}

/**
 * Para o polling
 */
function pararPolling() {
    if (intervalId) {
        clearInterval(intervalId);
        intervalId = null;
    }
}

/**
 * Verifica se há novas notificações não lidas
 */
async function verificarNovasNotificacoes() {
    try {
        const response = await fetch('/notificacoes/api/notificacoes/nao-lidas');
        const data = await response.json();
        
        if (data.sucesso) {
            atualizarBadge(data.count);
            
            // Se há notificações não lidas, buscar detalhes
            if (data.count > 0) {
                await buscarNotificacoesDetalhes();
            }
        }
    } catch (error) {
        console.error('❌ Erro ao verificar notificações:', error);
    }
}

/**
 * Busca detalhes das notificações recentes
 */
async function buscarNotificacoesDetalhes() {
    try {
        const response = await fetch(`/notificacoes/api/notificacoes?limite=${CONFIG.MAX_NOTIFICACOES_DROPDOWN}&apenas_nao_lidas=true`);
        const data = await response.json();
        
        if (data.sucesso && data.notificacoes.length > 0) {
            // Verificar se há notificações realmente novas
            const notificacoesNovas = data.notificacoes.filter(n => n.id > ultimoIdNotificacao);
            
            if (notificacoesNovas.length > 0) {
                // Atualizar último ID
                ultimoIdNotificacao = Math.max(...notificacoesNovas.map(n => n.id));
                
                // Tocar som e animar
                tocarSom();
                animarSino();
                
                // Atualizar dropdown
                atualizarDropdown(data.notificacoes);
            }
        }
    } catch (error) {
        console.error('❌ Erro ao buscar detalhes das notificações:', error);
    }
}

/**
 * Atualiza o badge do sino com o contador
 */
function atualizarBadge(count) {
    const badge = document.getElementById('notificacao-badge');
    if (!badge) return;
    
    if (count > 0) {
        badge.textContent = count > 99 ? '99+' : count;
        badge.style.display = 'inline-block';
        badge.classList.add('pulse');
    } else {
        badge.style.display = 'none';
        badge.classList.remove('pulse');
    }
}

/**
 * Toca o som de notificação usando Web Audio API
 */
function tocarSom() {
    if (somMutado || !audioContext) return;
    
    try {
        // Criar um som de "ding" (campainha) usando Web Audio API
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();
        
        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);
        
        // Configurar o som (frequência e duração)
        oscillator.frequency.value = 800; // Frequência da campainha
        oscillator.type = 'sine'; // Onda senoidal (som suave)
        
        // Envelope de volume (fade in/out)
        gainNode.gain.setValueAtTime(0, audioContext.currentTime);
        gainNode.gain.linearRampToValueAtTime(0.3, audioContext.currentTime + 0.01);
        gainNode.gain.linearRampToValueAtTime(0, audioContext.currentTime + 0.5);
        
        // Tocar o som
        oscillator.start(audioContext.currentTime);
        oscillator.stop(audioContext.currentTime + 0.5);
        
        console.log('🔊 Som de notificação tocado');
    } catch (error) {
        console.error('❌ Erro ao tocar som:', error);
    }
}

/**
 * Anima o sino (pulsar)
 */
function animarSino() {
    const sino = document.getElementById('sino-notificacao');
    if (!sino) return;
    
    sino.classList.add('shake');
    
    setTimeout(() => {
        sino.classList.remove('shake');
    }, CONFIG.DURACAO_ANIMACAO);
}

/**
 * Atualiza o dropdown com as notificações
 */
function atualizarDropdown(notificacoes) {
    const dropdown = document.getElementById('notificacoes-dropdown');
    if (!dropdown) return;
    
    if (notificacoes.length === 0) {
        dropdown.innerHTML = `
            <div class="dropdown-header">
                <h4>🔔 Notificações</h4>
            </div>
            <div class="dropdown-body">
                <p class="text-muted text-center py-3">Nenhuma notificação</p>
            </div>
        `;
        return;
    }
    
    const notificacoesHTML = notificacoes.map(n => {
        const tempoRelativo = calcularTempoRelativo(n.criada_em);
        const link = n.link || '#';
        
        return `
            <div class="notificacao-item ${n.lida ? '' : 'nao-lida'}" 
                 data-id="${n.id}" 
                 data-link="${link}"
                 onclick="clicarNotificacao(${n.id}, '${link}')">
                <div class="notificacao-icone" style="background-color: ${getCorHex(n.cor)}">
                    ${n.icone}
                </div>
                <div class="notificacao-conteudo">
                    <div class="notificacao-titulo">${n.titulo}</div>
                    <div class="notificacao-tempo">${tempoRelativo}</div>
                </div>
            </div>
        `;
    }).join('');
    
    dropdown.innerHTML = `
        <div class="dropdown-header">
            <h4>🔔 Notificações</h4>
            <button class="btn btn-sm btn-link" onclick="marcarTodasComoLidas()">
                Marcar todas como lidas
            </button>
        </div>
        <div class="dropdown-body">
            ${notificacoesHTML}
        </div>
        <div class="dropdown-footer">
            <a href="/notificacoes" class="btn btn-link btn-sm">
                Ver todas as notificações →
            </a>
        </div>
    `;
}

/**
 * Calcula tempo relativo (ex: "há 5 minutos")
 */
function calcularTempoRelativo(dataISO) {
    const data = new Date(dataISO);
    const agora = new Date();
    const diffSegundos = Math.floor((agora - data) / 1000);
    
    if (diffSegundos < 60) return 'agora mesmo';
    if (diffSegundos < 3600) return `há ${Math.floor(diffSegundos / 60)} min`;
    if (diffSegundos < 86400) return `há ${Math.floor(diffSegundos / 3600)}h`;
    return `há ${Math.floor(diffSegundos / 86400)} dias`;
}

/**
 * Converte cor nome para hex
 */
function getCorHex(cor) {
    const cores = {
        'red': '#dc3545',
        'green': '#28a745',
        'blue': '#007bff',
        'orange': '#fd7e14',
        'purple': '#6f42c1',
        'gray': '#6c757d'
    };
    return cores[cor] || cores['gray'];
}

/**
 * Clique em uma notificação
 */
async function clicarNotificacao(id, link) {
    try {
        // Marcar como lida
        await fetch(`/notificacoes/api/notificacoes/${id}/ler`, {
            method: 'POST'
        });
        
        // Redirecionar
        if (link && link !== '#') {
            window.location.href = link;
        }
    } catch (error) {
        console.error('❌ Erro ao clicar na notificação:', error);
    }
}

/**
 * Marca todas as notificações como lidas
 */
async function marcarTodasComoLidas() {
    try {
        await fetch('/notificacoes/api/notificacoes/ler-todas', {
            method: 'POST'
        });
        
        // Atualizar badge
        atualizarBadge(0);
        
        // Atualizar dropdown
        const dropdown = document.getElementById('notificacoes-dropdown');
        if (dropdown) {
            dropdown.querySelectorAll('.notificacao-item').forEach(item => {
                item.classList.remove('nao-lida');
            });
        }
        
        console.log('✅ Todas as notificações marcadas como lidas');
    } catch (error) {
        console.error('❌ Erro ao marcar todas como lidas:', error);
    }
}

/**
 * Alterna o som entre mutado/não mutado
 */
function toggleSom() {
    somMutado = !somMutado;
    localStorage.setItem('notificacao_som_mutado', somMutado);
    atualizarBotaoSom();
    
    console.log(somMutado ? '🔇 Som mutado' : '🔊 Som ativado');
}

/**
 * Atualiza o ícone do botão de som
 */
function atualizarBotaoSom() {
    const botao = document.getElementById('btn-toggle-som');
    if (!botao) return;
    
    if (somMutado) {
        botao.innerHTML = '🔇';
        botao.title = 'Ativar som';
    } else {
        botao.innerHTML = '🔊';
        botao.title = 'Mutar som';
    }
}

/**
 * Configura event listeners
 */
function configurarEventListeners() {
    // Toggle do dropdown
    const sino = document.getElementById('sino-notificacao');
    if (sino) {
        sino.addEventListener('click', function(e) {
            e.stopPropagation();
            const dropdown = document.getElementById('notificacoes-dropdown');
            if (dropdown) {
                dropdown.style.display = dropdown.style.display === 'none' ? 'block' : 'none';
            }
        });
    }
    
    // Fechar dropdown ao clicar fora
    document.addEventListener('click', function(e) {
        const dropdown = document.getElementById('notificacoes-dropdown');
        const sino = document.getElementById('sino-notificacao');
        
        if (dropdown && sino && !sino.contains(e.target) && !dropdown.contains(e.target)) {
            dropdown.style.display = 'none';
        }
    });
}
