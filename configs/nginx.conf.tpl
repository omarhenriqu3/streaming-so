# Template usado pelo orquestrador (os marcadores @...@ são substituídos em tempo de execução).
# Um único worker, para que "o processo do servidor" seja um só e possa ser isolado.
user root;             # evita 403 quando o projeto está numa pasta pessoal (home 750)
worker_processes 1;
daemon on;
pid @RUNDIR@/nginx.pid;
error_log @RUNDIR@/error.log warn;

events {
    worker_connections 1024;
}

http {
    access_log off;
    sendfile off;          # força o servidor a copiar os dados (mais CPU por requisição)
    tcp_nopush off;
    default_type application/octet-stream;
    client_body_temp_path @RUNDIR@/tmp_body;
    proxy_temp_path @RUNDIR@/tmp_proxy;
    fastcgi_temp_path @RUNDIR@/tmp_fcgi;
    uwsgi_temp_path @RUNDIR@/tmp_uwsgi;
    scgi_temp_path @RUNDIR@/tmp_scgi;

    server {
        listen 127.0.0.1:@PORTA@;
        root @VIDEODIR@;
        location / { try_files $uri =404; }
    }
}
