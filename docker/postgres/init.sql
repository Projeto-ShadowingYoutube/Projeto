-- Executado pelo container do Postgres apenas na primeira inicialização do volume.
-- Banco exclusivo do pytest (TEST_DATABASE_URL): os testes apagam e recriam tabelas,
-- então nunca podem apontar para o banco "shadowing", que guarda os dados de desenvolvimento.
CREATE DATABASE shadowing_teste;
