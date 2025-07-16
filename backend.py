from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from datetime import timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, date
from flask_mail import Mail, Message
from flask_cors import CORS
hoje = date.today()
import requests, re, os

# Configuração do app
app = Flask(__name__)

CORS(app, origins=["*"], supports_credentials=True)
@app.after_request
def aplicar_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response

#app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///sistema_cotacao.db'  # Trocar para PostgreSQL em produção
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://vivaz_db_user:zPAolmu8BzplatFF8lTtoHdZZI1EZkM9@dpg-d1s0v86mcj7s73ebv1g0-a:5432/vivaz_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = 'supersecretkey'  # Alterar para produção

# Configuração do Flask-Mail
app.config['MAIL_SERVER'] = 'smtp.gmail.com'  # Servidor SMTP (use o seu)
app.config['MAIL_PORT'] = 587  # Porta SMTP
app.config['MAIL_USE_TLS'] = True  # Usar TLS para segurança
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
mail = Mail(app)

# Configurando datas para o prazo das cotações
def add_business_days(start_date, num_days):
    """Adiciona apenas dias úteis à data inicial."""
    current_date = start_date
    while num_days > 0:
        current_date += timedelta(days=1)
        # Se o dia não for sábado (5) ou domingo (6), conta como um dia útil
        if current_date.weekday() < 5:
            num_days -= 1
    return current_date

# Inicializando
jwt = JWTManager(app)
db = SQLAlchemy(app)

# Modelos
class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    senha = db.Column(db.String(200), nullable=False)
    cargo = db.Column(db.String(50), nullable=False)  # Sindico, Conselheiro, Administrador
    periodo_gestao = db.Column(db.String(20), nullable=False)
    device_token = db.Column(db.String(255), nullable=True)  

    def serialize(self):
        return {'id': self.id, 'nome': self.nome, 'email': self.email, 'cargo': self.cargo, 'periodo_gestao': self.periodo_gestao, 'device_token' : self.device_token}

class Fornecedor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    contato = db.Column(db.String(100), nullable=False)
    historico_negociacoes = db.Column(db.Text, nullable=True)

    def serialize(self):
        return {'id': self.id, 'nome': self.nome, 'contato': self.contato, 'historico_negociacoes': self.historico_negociacoes}

class Cotacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    solicitante_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    descricao = db.Column(db.String(200), nullable=False)
    data_solicitacao = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    prazo_votacao = db.Column(db.DateTime, nullable=False, default=lambda: add_business_days(datetime.utcnow(), 2))
    status = db.Column(db.String(50), nullable=False, default='Pendente')
    proposta_vencedora_id = db.Column(db.Integer, db.ForeignKey('proposta.id'), nullable=True)

    def serialize(self):
        return {'id': self.id,'solicitante_id': self.solicitante_id,'descricao': self.descricao,'data_solicitacao': self.data_solicitacao,'prazo_votacao': self.prazo_votacao,'status': self.status,'proposta_vencedora_id': self.proposta_vencedora_id}

class Proposta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cotacao_id = db.Column(db.Integer, db.ForeignKey('cotacao.id'), nullable=False)
    fornecedor_id = db.Column(db.Integer, db.ForeignKey('fornecedor.id'), nullable=False)
    item = db.Column(db.String(200), nullable=False)   
    valor = db.Column(db.Float, nullable=False)
    prazo_entrega = db.Column(db.String(50), nullable=True)   
    link = db.Column(db.String(255), nullable=True)  
    observacoes = db.Column(db.Text, nullable=True)

    def serialize(self):
        return {
            'id': self.id,
            'cotacao_id': self.cotacao_id,
            'fornecedor_id': self.fornecedor_id,
            'item': self.item,
            'valor': self.valor,
            'prazo_entrega': self.prazo_entrega,
            'link': self.link,
            'observacoes': self.observacoes
        }

class Votacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cotacao_id = db.Column(db.Integer, db.ForeignKey('cotacao.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    proposta_id = db.Column(db.Integer, db.ForeignKey('proposta.id'), nullable=False)
    voto = db.Column(db.String(10), nullable=False)  # 'Aprovar' ou 'Rejeitar'
    justificativa = db.Column(db.Text, nullable=True)

    def serialize(self):
        return {
            'id': self.id,
            'cotacao_id': self.cotacao_id,
            'usuario_id': self.usuario_id,
            'proposta_id': self.proposta_id,
            'voto': self.voto,
            'justificativa': self.justificativa
        }

class Notificacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    mensagem = db.Column(db.String(255), nullable=False)
    data_envio = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    lida = db.Column(db.Boolean, default=False)

    def serialize(self):
        return {
            'id': self.id,
            'usuario_id': self.usuario_id,
            'mensagem': self.mensagem,
            'data_envio': self.data_envio,
            'lida': self.lida
        }

def enviar_push_notification(device_token, titulo, mensagem):
    url = 'https://exp.host/--/api/v2/push/send'
    payload = {
        'to': device_token,
        'title': titulo,
        'body': mensagem
    }
    response = requests.post(url, json=payload)
    print("🔔 Push enviado:", response.status_code, response.text)

def enviar_notificacao(usuario_id, mensagem):
    usuario = Usuario.query.get(usuario_id)
    nova_notificacao = Notificacao(usuario_id=usuario_id, mensagem=mensagem)
    db.session.add(nova_notificacao)
    db.session.commit()

    mensagem_sem_tags = re.sub(r'<[^>]+>', '', mensagem)
    
    # 🔔 Envia push também se tiver device_token
    if usuario.device_token:
        enviar_push_notification(usuario.device_token, "Vivaz Cotações", mensagem_sem_tags)

def enviar_email(destinatarios, assunto, mensagem):
    msg = Message(assunto, sender="seuemail@gmail.com", recipients=destinatarios)
    msg.body = mensagem
    mail.send(msg)


# Rota de cadastro de usuário
@app.route('/cadastro', methods=['POST'])
@jwt_required()
def cadastro():
    #Verifica administrador
    usuario_id = get_jwt_identity()
    usuario = Usuario.query.get(usuario_id)
    if not usuario or usuario.cargo.lower() != "admin":
        return jsonify({'message': 'Apenas o Administrador pode criar usuários!'}), 403
    
    data = request.get_json()
    senha_hash = generate_password_hash(data['senha'])
    novo_usuario = Usuario(nome=data['nome'], email=data['email'], senha=senha_hash, cargo=data['cargo'], periodo_gestao=data['periodo_gestao'])
    db.session.add(novo_usuario)
    db.session.commit()
    return jsonify({'message': 'Usuário cadastrado com sucesso!'}), 201

# Rota de login
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    usuario = Usuario.query.filter_by(email=data['email']).first()

    if usuario and check_password_hash(usuario.senha, data['senha']):
        access_token = create_access_token(
            identity=str(usuario.id),
            expires_delta=timedelta(days=1),
            additional_claims={"nome": usuario.nome, "cargo": usuario.cargo}
        )
        return jsonify({'token': access_token})
    
    return jsonify({'message': 'Credenciais inválidas'}), 401

# Rota para cadastrar fornecedor
@app.route('/fornecedor', methods=['POST'])
@jwt_required()
def cadastrar_fornecedor():
    data = request.get_json()
    
    novo_fornecedor = Fornecedor(
        nome=data['nome'],
        contato=data['contato'],
        historico_negociacoes=data.get('historico_negociacoes', '')
    )
    
    db.session.add(novo_fornecedor)
    db.session.commit()
    
    return jsonify({'message': 'Fornecedor cadastrado com sucesso!', 'fornecedor': novo_fornecedor.serialize()}), 201

# Rota para listar fornecedores
@app.route('/fornecedores', methods=['GET'])
@jwt_required()
def listar_fornecedores():
    fornecedores = Fornecedor.query.all()
    return jsonify({'fornecedores': [fornecedor.serialize() for fornecedor in fornecedores]})

# Rota para solicitar cotação
@app.route('/cotacao', methods=['POST'])
@jwt_required()
def solicitar_cotacao():
    usuario_id = get_jwt_identity()
    usuario = Usuario.query.get(usuario_id)

    # Permitir apenas Síndicos a criar cotações
    if not usuario or usuario.cargo.lower() != "síndico":
        return jsonify({'message': 'Apenas o Síndico pode criar cotações!'}), 403

    data = request.get_json()
    nova_cotacao = Cotacao(
        solicitante_id=usuario_id,
        descricao=data['descricao']
    )

    db.session.add(nova_cotacao)
    db.session.commit()

    # Enviar notificação para todos os Conselheiros
    conselheiros = Usuario.query.filter_by(cargo="Conselho").all()
    mensagem = f"<strong>Nova cotação:</strong> {nova_cotacao.descricao}."

    for conselheiro in conselheiros:
        enviar_notificacao(conselheiro.id, mensagem)
    
    return jsonify({'message': 'Cotação cadastrada com sucesso!', 'cotacao': nova_cotacao.serialize()}), 201

# Rota para listar cotações
@app.route('/cotacoes', methods=['GET'])
@jwt_required()
def listar_cotacoes():
    cotacoes = Cotacao.query.all()
    return jsonify({'cotacoes': [cotacao.serialize() for cotacao in cotacoes]})

# Rota para cadastrar proposta
@app.route('/propostas', methods=['POST'])
@jwt_required()
def cadastrar_proposta():
    data = request.get_json()

    nova_proposta = Proposta(
        cotacao_id=data['cotacao_id'],
        fornecedor_id=data['fornecedor_id'],
        item=data['item'], 
        valor=data['valor'],
        prazo_entrega=data.get('prazo_entrega', ''),  
        link=data.get('link', ''),  
        observacoes=data.get('observacoes', '')   
    )

    db.session.add(nova_proposta)

    # Atualizar o prazo de votação
    cotacao = Cotacao.query.get(data['cotacao_id'])
    if cotacao:
        cotacao.prazo_votacao = add_business_days(datetime.utcnow(), 2)  # Atualiza para 2 dias úteis a partir de hoje
        db.session.add(cotacao)

    #Enviar notificação para os conselheiros
    conselheiros = Usuario.query.filter_by(cargo="Conselho").all()
    mensagem = f"<strong>Nova proposta em:</strong> {cotacao.descricao}!"

    for conselheiro in conselheiros:
        enviar_notificacao(conselheiro.id, mensagem)

    db.session.commit()

    return jsonify({
        'message': 'Proposta cadastrada com sucesso!',
        'proposta': nova_proposta.serialize()
    }), 201

# Rota para listar propostas de uma cotação
@app.route('/propostas/<int:cotacao_id>', methods=['GET'])
@jwt_required()
def listar_propostas(cotacao_id):
    propostas = Proposta.query.filter_by(cotacao_id=cotacao_id).all()
    return jsonify({
        'propostas': [proposta.serialize() for proposta in propostas]})

# SEM USO ACHO // Rota para listar e comparar propostas de uma cotação específica
@app.route('/comparar_propostas/<int:cotacao_id>', methods=['GET'])
@jwt_required()
def comparar_propostas(cotacao_id):
    propostas = Proposta.query.filter_by(cotacao_id=cotacao_id).order_by(Proposta.valor.asc()).all()
    return jsonify({'cotacao_id': cotacao_id, 'propostas': [proposta.serialize() for proposta in propostas]})

#Rota para registrar voto
@app.route('/votacao', methods=['POST'])
@jwt_required()
def registrar_voto():
    data = request.get_json()
    usuario_id = get_jwt_identity()

    # Verifica se o usuário já votou nessa cotação
    voto_existente = Votacao.query.filter_by(
        cotacao_id=data['cotacao_id'],
        usuario_id=usuario_id
    ).first()

    if voto_existente:
        return jsonify({'message': 'Você já votou nesta cotação!'}), 400  # Retorna erro se o usuário já votou

     # Obtém os dados do usuário logado
    usuario = Usuario.query.get(usuario_id)
    if not usuario:
        return jsonify({'message': 'Usuário não encontrado!'}), 404
    
     # Obtém a cotação votada
    cotacao = Cotacao.query.get(data['cotacao_id'])
    if not cotacao:
        return jsonify({'message': 'Cotação não encontrada!'}), 404

    # Criação do novo voto
    novo_voto = Votacao(
        cotacao_id=data['cotacao_id'],
        usuario_id=usuario_id,
        proposta_id=data['proposta_id'],
        voto=data['voto'],
        justificativa=data.get('justificativa', '')
    )

    db.session.add(novo_voto)

    #Enviar notificação para os síndicos
    sindicos = Usuario.query.filter_by(cargo="Síndico").all()
    mensagem = f"<strong>{usuario.nome} votou em em:</strong> {cotacao.descricao}!"

    for sindico in sindicos:
        enviar_notificacao(sindico.id, mensagem)

    db.session.commit()

    return jsonify({'message': 'Voto registrado com sucesso!', 'votacao': novo_voto.serialize()}), 201

#Rota para listar votação
@app.route('/votacoes/<int:cotacao_id>', methods=['GET'])
@jwt_required()
def listar_votacoes(cotacao_id):
    votacoes = Votacao.query.filter_by(cotacao_id=cotacao_id).all()
    resultado = []

    for voto in votacoes:
        usuario = Usuario.query.get(voto.usuario_id)
        proposta = Proposta.query.get(voto.proposta_id)

        resultado.append({
            'id': voto.id,
            'usuario_id': usuario.id if usuario else None,
            'nome_usuario': usuario.nome if usuario else "Usuário não encontrado",
            'fornecedor': proposta.fornecedor_id if proposta else "Fornecedor não encontrado",
            'item': proposta.item if proposta else "Item não encontrado",
            'voto': voto.voto,
            'justificativa': voto.justificativa
        })

    return jsonify({'votacoes': resultado})

@app.route('/cotacao/vencedora/<int:cotacao_id>', methods=['POST'])
@jwt_required()
def definir_proposta_vencedora(cotacao_id):
    data = request.get_json()
    cotacao = Cotacao.query.get(cotacao_id)

    if not cotacao:
        return jsonify({'message': 'Cotação não encontrada'}), 404

    if cotacao.status == 'Finalizada':
        return jsonify({'message': 'Esta cotação já foi finalizada'}), 400

    proposta = Proposta.query.get(data.get('proposta_vencedora_id'))

    if not proposta or proposta.cotacao_id != cotacao_id:
        return jsonify({'message': 'Proposta inválida ou não pertence a esta cotação'}), 400

    cotacao.proposta_vencedora_id = proposta.id
    cotacao.status = 'Finalizada'

    # Enviar notificação para o solicitante da cotação
    mensagem = f"Sua cotação '{cotacao.descricao}' foi finalizada. Proposta vencedora: {proposta.valor}."
    enviar_notificacao(cotacao.solicitante_id, mensagem)

    # Buscar e-mails dos membros do conselho e síndico
    usuarios_notificar = Usuario.query.filter(Usuario.cargo.in_(['Síndico', 'Conselho'])).all()
    emails_destinatarios = [usuario.email for usuario in usuarios_notificar]

    if emails_destinatarios:
        enviar_email(
            emails_destinatarios,
            "Cotação Finalizada",
            f"A cotação '{cotacao.descricao}' foi finalizada. Proposta vencedora: {proposta.valor}."
        )

    db.session.commit()

    return jsonify({
        'message': 'Proposta vencedora definida com sucesso, notificação enviada e e-mails disparados!',
        'cotacao': cotacao.serialize()
    }), 200

#Rota para listar notificações
@app.route('/notificacoes', methods=['GET'])
@jwt_required()
def listar_notificacoes():
    usuario_id = get_jwt_identity()
    notificacoes = Notificacao.query.filter_by(usuario_id=usuario_id).order_by(Notificacao.data_envio.desc()).all()
    
    return jsonify({'notificacoes': [notificacao.serialize() for notificacao in notificacoes]})

#Rota para excluir cotação
@app.route('/cotacao/<int:cotacao_id>', methods=['DELETE'])
@jwt_required()
def excluir_cotacao(cotacao_id):
    usuario_id = get_jwt_identity()
    usuario = Usuario.query.get(usuario_id)

    if not usuario or usuario.cargo != "Síndico":
        return jsonify({'message': 'Apenas o síndico pode excluir cotações'}), 403

    cotacao = Cotacao.query.get(cotacao_id)

    if not cotacao:
        return jsonify({'message': 'Cotação não encontrada'}), 404

    # Excluir todas as propostas relacionadas à cotação
    Proposta.query.filter_by(cotacao_id=cotacao_id).delete()

    # Excluir todos os votos relacionados à cotação
    Votacao.query.filter_by(cotacao_id=cotacao_id).delete()

    # Excluir a cotação
    db.session.delete(cotacao)
    db.session.commit()

    return jsonify({'message': 'Cotação e propostas associadas excluídas com sucesso'}), 200

#ROTA PARA EXCLUIR PROPOSTA INDIVIDUAL
@app.route('/propostas/<int:proposta_id>', methods=['DELETE'])
@jwt_required()
def excluir_proposta(proposta_id):
    proposta = Proposta.query.get(proposta_id)
    
    if not proposta:
        return jsonify({'message': 'Proposta não encontrada'}), 404

    db.session.delete(proposta)
    db.session.commit()
    
    return jsonify({'message': 'Proposta excluída com sucesso'}), 200

#ROTA PARA EXCLUIR VOTO INDIVIDUAL
@app.route('/votacao/<int:voto_id>', methods=['DELETE'])
@jwt_required()
def excluir_voto(voto_id):
    usuario_id = get_jwt_identity()  # Obtém o ID do usuário autenticado

    # Busca o voto no banco de dados
    voto = Votacao.query.get(voto_id)

    # Verifica se o voto existe
    if not voto:
        return jsonify({'message': 'Voto não encontrado'}), 404

    # Verifica se o usuário tem permissão para excluir este voto
    if voto.usuario_id != int(usuario_id):
        return jsonify({'message': 'Você só pode excluir o seu próprio voto'}), 403

    # Remove o voto do banco de dados
    db.session.delete(voto)
    db.session.commit()

    return jsonify({'message': 'Voto excluído com sucesso'}), 200

# Rota para obter detalhes de uma cotação específica
@app.route('/cotacao/<int:cotacao_id>', methods=['GET'])
@jwt_required()
def obter_cotacao(cotacao_id):
    usuario_id = get_jwt_identity()
    cotacao = Cotacao.query.get(cotacao_id)
    if not cotacao:
        return jsonify({"message": "Cotação não encontrada"}), 404

    # Apagar notificações vinculadas a essa cotação para o usuário logado
    notificacoes_apagadas = Notificacao.query.filter(
        Notificacao.usuario_id == usuario_id,
        Notificacao.mensagem.like(f"%{cotacao.descricao}%")
    ).delete()

    db.session.commit()
    
    return jsonify({
        'id': cotacao.id,
        'descricao': cotacao.descricao,
        'prazo_votacao': cotacao.prazo_votacao.strftime("%d/%m/%Y") if cotacao.prazo_votacao else "Sem prazo definido",
        'status': cotacao.status
    })

#FINALIZANDO COTAÇÕES VENCIDAS
@app.route('/finalizar_cotacoes', methods=['POST'])
@jwt_required()
def finalizar_cotacoes():
    try:
        cotacoes_vencidas = Cotacao.query.filter(Cotacao.prazo_votacao < hoje, Cotacao.status != "Finalizada").all()

        if not cotacoes_vencidas:
            return jsonify({"message": "Nenhuma cotação vencida encontrada."}), 400
        
        for cotacao in cotacoes_vencidas:
            cotacao.status = "Finalizada"
        
        #Enviar notificação para os conselheiros
        conselheiros = Usuario.query.filter_by(cargo="Conselho").all()
        mensagem = f"<strong>Cotação Finalizada:</strong> {cotacao.descricao}!"

        for conselheiro in conselheiros:
            enviar_notificacao(conselheiro.id, mensagem)
            db.session.commit()

        return jsonify({"message": "Cotações finalizadas com sucesso!"}), 200

    except Exception as e:
        print("Erro ao finalizar cotações:", str(e))
        return jsonify({"message": "Erro ao finalizar cotações."}), 500


#REABRIR COTAÇÃO
@app.route('/reabrir_cotacao/<int:cotacao_id>', methods=['POST'])
@jwt_required()
def reabrir_cotacao(cotacao_id):
    usuario_id = get_jwt_identity()
    usuario = Usuario.query.get(usuario_id)

    if not usuario or usuario.cargo != "Síndico":
        return jsonify({'error': 'Apenas o síndico pode reabrir cotações'}), 403

    cotacao = Cotacao.query.get(cotacao_id)

    if not cotacao:
        return jsonify({'error': 'Cotação não encontrada'}), 404

    if cotacao.status != 'Finalizada':
        return jsonify({'error': 'Apenas cotações finalizadas podem ser reabertas'}), 400

    cotacao.status = 'Reaberta'

    #Atualiza o prazo
    cotacao.prazo_votacao = add_business_days(datetime.utcnow(), 2)

    #Enviar notificação para os conselheiros
    conselheiros = Usuario.query.filter_by(cargo="Conselho").all()
    mensagem = f"<strong>Cotação reaberta:</strong> {cotacao.descricao}!"

    for conselheiro in conselheiros:
        enviar_notificacao(conselheiro.id, mensagem)

    db.session.commit()
    db.session.refresh(cotacao)
    
    return jsonify({'message': 'Cotação reaberta com sucesso', 'cotacao': cotacao.serialize()}), 200

#ROTA DELETAR NOTIFICAÇÕES
@app.route('/notificacoes/<int:notificacao_id>', methods=['DELETE'])
@jwt_required()
def deletar_notificacao(notificacao_id):
    notificacao = Notificacao.query.get(notificacao_id)
    
    if not notificacao:
        return jsonify({'message': 'Notificação não encontrada'}), 404
    
    db.session.delete(notificacao)
    db.session.commit()
    
    return jsonify({'message': 'Notificação deletada com sucesso!'}), 200


@app.route('/test-cors', methods=['GET'])
def test_cors():
    return jsonify({'message': 'CORS está funcionando!'}), 200

#ROTA REGISTRAR/ATUALIZAR TOKEN
@app.route('/registrar_device_token', methods=['POST'])
@jwt_required()
def registrar_device_token():
    usuario_id = get_jwt_identity()
    data = request.get_json()
    token = data.get('device_token')

    if not token:
        print(f"ℹ️ Nenhum token enviado — ignorado. Usuário: {usuario_id}")
        return jsonify({'message': 'Nenhum device token enviado.'}), 200
    
    usuario = Usuario.query.get(usuario_id)
    if not usuario:
        return jsonify({'message': 'Usuário não encontrado'}), 404

    usuario.device_token = token
    db.session.commit()
    return jsonify({'message': 'Device token registrado com sucesso!'}), 200

#Listar todos os usuários (somente Admin)
@app.route('/users', methods=['GET'])
@jwt_required()
def listar_usuarios():
    usuario_id = get_jwt_identity()
    usuario = Usuario.query.get(usuario_id)

    if not usuario or usuario.cargo.lower() != "admin":
        return jsonify({'message': 'Apenas o Administrador pode listar usuários!'}), 403

    usuarios = Usuario.query.all()
    return jsonify([u.serialize() for u in usuarios]), 200

#Excluir usuário (somente Admin)
@app.route('/users/<int:id>', methods=['DELETE'])
@jwt_required()
def excluir_usuario(id):
    usuario_id = get_jwt_identity()
    usuario = Usuario.query.get(usuario_id)

    if not usuario or usuario.cargo.lower() != "admin":
        return jsonify({'message': 'Apenas o Administrador pode excluir usuários!'}), 403

    usuario_excluir = Usuario.query.get(id)
    if not usuario_excluir:
        return jsonify({'message': 'Usuário não encontrado!'}), 404

    db.session.delete(usuario_excluir)
    db.session.commit()
    return jsonify({'message': 'Usuário excluído com sucesso!'}), 200

#Redefinir senha de usuário (somente Admin)
@app.route('/users/<int:id>/reset_senha', methods=['POST'])
@jwt_required()
def resetar_senha(id):
    usuario_id = get_jwt_identity()
    usuario = Usuario.query.get(usuario_id)

    if not usuario or usuario.cargo.lower() != "admin":
        return jsonify({'message': 'Apenas o Administrador pode redefinir senha!'}), 403

    data = request.get_json()
    nova_senha = generate_password_hash(data.get('nova_senha'))

    usuario_reset = Usuario.query.get(id)
    if not usuario_reset:
        return jsonify({'message': 'Usuário não encontrado!'}), 404

    usuario_reset.senha = nova_senha
    db.session.commit()
    return jsonify({'message': 'Senha redefinida com sucesso!'}), 200

@app.route("/redefinir-senha", methods=["POST"])
def esqueci_senha():
    data = request.get_json()
    email = data.get("email")

    usuario = Usuario.query.filter_by(email=email).first()
    if not usuario:
        return jsonify({"message": "E-mail não encontrado"}), 404

    # Cria token com validade de 30 min
    token = create_access_token(identity=usuario.id, expires_delta=datetime.timedelta(minutes=30))
    
    link = f"https://sistema-vivaz-frontend.vercel.app/nova-senha?token={token}"

    msg = Message("Redefinição de Senha", recipients=[email])
    msg.body = f"Olá {usuario.nome},\n\nClique no link para redefinir sua senha:\n\n{link}\n\nSe não foi você, ignore este e-mail."
    
    mail.send(msg)
    return jsonify({"message": "E-mail de redefinição enviado com sucesso!"})

@app.route("/nova-senha", methods=["POST"])
@jwt_required()
def nova_senha():
    usuario_id = get_jwt_identity()
    data = request.get_json()
    nova = data.get("nova_senha")

    usuario = Usuario.query.get(usuario_id)
    if not usuario:
        return jsonify({"message": "Usuário não encontrado"}), 404

    usuario.senha = generate_password_hash(nova)
    db.session.commit()

    return jsonify({"message": "Senha redefinida com sucesso!"})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()

        #Criar adm
        if not Usuario.query.filter_by(email="admin@vivaz.com").first():
                from werkzeug.security import generate_password_hash

                admin = Usuario(
                    nome="Administrador",
                    email="admin@vivaz.com",
                    senha=generate_password_hash("200817"),
                    cargo="Admin",
                    periodo_gestao="SEMPRE"
                )
                db.session.add(admin)
                db.session.commit()
                print("✅ Usuário admin criado!")
    app.run(host="0.0.0.0", port=5000, debug=True)
