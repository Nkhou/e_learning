# users/email_helpers.py
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags


def send_approval_email(user):
    """
    Envoie un email de confirmation d'approbation à un formateur ou une organisation
    """
    subject = 'Votre compte a été approuvé - Plateforme E-Learning'
    
    # Version HTML de l'email
    html_message = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #4CAF50; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; background-color: #f9f9f9; }}
            .button {{ 
                display: inline-block; 
                padding: 12px 24px; 
                background-color: #4CAF50; 
                color: white; 
                text-decoration: none; 
                border-radius: 5px; 
                margin: 20px 0; 
            }}
            .footer {{ padding: 20px; text-align: center; font-size: 12px; color: #777; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Félicitations ! 🎉</h1>
            </div>
            <div class="content">
                <h2>Bonjour {user.first_name} {user.last_name},</h2>
                
                <p>Nous avons le plaisir de vous informer que votre compte <strong>{"Formateur" if user.privilege == "F" else "Organisation"}</strong> 
                a été approuvé par notre équipe !</p>
                
                <p>Vous pouvez maintenant accéder à toutes les fonctionnalités de la plateforme et commencer à 
                {"créer et partager vos formations" if user.privilege == "F" else "gérer vos groupes et formations"}.</p>
                
                <div style="text-align: center;">
                    <a href="{settings.FRONTEND_URL}/login" class="button">Accéder à la plateforme</a>
                </div>
                
                <p><strong>Prochaines étapes :</strong></p>
                <ul>
                    <li>Connectez-vous à votre compte</li>
                    {"<li>Créez votre première formation</li>" if user.privilege == "F" else "<li>Créez vos premiers groupes</li>"}
                    <li>Explorez les fonctionnalités disponibles</li>
                    {"<li>Partagez vos connaissances avec les apprenants</li>" if user.privilege == "F" else "<li>Ajoutez vos membres et assignez des formations</li>"}
                </ul>
                
                <p>Si vous avez des questions, n'hésitez pas à nous contacter.</p>
                
                <p>Cordialement,<br>
                L'équipe E-Learning Platform</p>
            </div>
            <div class="footer">
                <p>© 2024 E-Learning Platform. Tous droits réservés.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    # Version texte de l'email (fallback)
    text_message = f"""
    Bonjour {user.first_name} {user.last_name},

    Félicitations ! Votre compte {"Formateur" if user.privilege == "F" else "Organisation"} a été approuvé.

    Vous pouvez maintenant accéder à la plateforme E-Learning et commencer à 
    {"créer et partager vos formations" if user.privilege == "F" else "gérer vos groupes et formations"}.

    Connectez-vous dès maintenant : {settings.FRONTEND_URL}/login

    Prochaines étapes :
    - Connectez-vous à votre compte
    {"- Créez votre première formation" if user.privilege == "F" else "- Créez vos premiers groupes"}
    - Explorez les fonctionnalités disponibles

    Cordialement,
    L'équipe E-Learning Platform
    """
    
    try:
        send_mail(
            subject=subject,
            message=text_message,
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Error sending approval email: {str(e)}")
        return False


def send_rejection_email(user, reason):
    """
    Envoie un email de notification de rejet à un formateur ou une organisation
    """
    subject = 'Mise à jour de votre demande - Plateforme E-Learning'
    
    # Version HTML de l'email
    html_message = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #f44336; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; background-color: #f9f9f9; }}
            .reason-box {{ 
                background-color: #fff3cd; 
                border-left: 4px solid #ffc107; 
                padding: 15px; 
                margin: 20px 0; 
            }}
            .button {{ 
                display: inline-block; 
                padding: 12px 24px; 
                background-color: #2196F3; 
                color: white; 
                text-decoration: none; 
                border-radius: 5px; 
                margin: 20px 0; 
            }}
            .footer {{ padding: 20px; text-align: center; font-size: 12px; color: #777; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Mise à jour de votre demande</h1>
            </div>
            <div class="content">
                <h2>Bonjour {user.first_name} {user.last_name},</h2>
                
                <p>Nous vous remercions pour votre intérêt pour notre plateforme E-Learning.</p>
                
                <p>Après examen de votre demande de compte <strong>{"Formateur" if user.privilege == "F" else "Organisation"}</strong>, 
                nous regrettons de vous informer que nous ne pouvons pas l'approuver pour le moment.</p>
                
                <div class="reason-box">
                    <strong>Raison :</strong><br>
                    {reason or "Aucune raison spécifique fournie"}
                </div>
                
                <p><strong>Que faire maintenant ?</strong></p>
                <ul>
                    <li>Vous pouvez soumettre une nouvelle demande après avoir pris en compte les points mentionnés</li>
                    <li>Contactez-nous si vous avez besoin de clarifications</li>
                    <li>Consultez nos critères d'éligibilité sur notre site web</li>
                </ul>
                
                <div style="text-align: center;">
                    <a href="{settings.FRONTEND_URL}/contact" class="button">Nous contacter</a>
                </div>
                
                <p>Nous vous souhaitons le meilleur dans vos projets.</p>
                
                <p>Cordialement,<br>
                L'équipe E-Learning Platform</p>
            </div>
            <div class="footer">
                <p>© 2024 E-Learning Platform. Tous droits réservés.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    # Version texte de l'email (fallback)
    text_message = f"""
    Bonjour {user.first_name} {user.last_name},

    Nous vous remercions pour votre intérêt pour notre plateforme E-Learning.

    Après examen de votre demande, nous ne pouvons pas l'approuver pour le moment.

    Raison : {reason or "Aucune raison spécifique fournie"}

    Que faire maintenant ?
    - Vous pouvez soumettre une nouvelle demande après avoir pris en compte les points mentionnés
    - Contactez-nous si vous avez besoin de clarifications
    - Consultez nos critères d'éligibilité

    Contactez-nous : {settings.FRONTEND_URL}/contact

    Cordialement,
    L'équipe E-Learning Platform
    """
    
    try:
        send_mail(
            subject=subject,
            message=text_message,
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Error sending rejection email: {str(e)}")
        return False


def send_suspension_email(user, reason):
    """
    Envoie un email de notification de suspension à un utilisateur
    """
    subject = 'Votre compte a été suspendu - Plateforme E-Learning'
    
    html_message = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #ff9800; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; background-color: #f9f9f9; }}
            .warning-box {{ 
                background-color: #fff3cd; 
                border-left: 4px solid #ff9800; 
                padding: 15px; 
                margin: 20px 0; 
            }}
            .footer {{ padding: 20px; text-align: center; font-size: 12px; color: #777; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>⚠️ Suspension de compte</h1>
            </div>
            <div class="content">
                <h2>Bonjour {user.first_name} {user.last_name},</h2>
                
                <p>Nous vous informons que votre compte sur la plateforme E-Learning a été temporairement suspendu.</p>
                
                <div class="warning-box">
                    <strong>Raison de la suspension :</strong><br>
                    {reason or "Violation des conditions d'utilisation"}
                </div>
                
                <p>Pendant cette période, vous ne pourrez pas accéder à la plateforme ni à vos contenus.</p>
                
                <p><strong>Pour réactiver votre compte :</strong></p>
                <ul>
                    <li>Contactez notre équipe de support</li>
                    <li>Fournissez toute information demandée</li>
                    <li>Respectez les conditions d'utilisation de la plateforme</li>
                </ul>
                
                <p>Si vous pensez qu'il s'agit d'une erreur, veuillez nous contacter immédiatement.</p>
                
                <p>Cordialement,<br>
                L'équipe E-Learning Platform</p>
            </div>
            <div class="footer">
                <p>© 2024 E-Learning Platform. Tous droits réservés.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    text_message = f"""
    Bonjour {user.first_name} {user.last_name},

    Votre compte sur la plateforme E-Learning a été temporairement suspendu.

    Raison : {reason or "Violation des conditions d'utilisation"}

    Pour réactiver votre compte, veuillez contacter notre équipe de support.

    Cordialement,
    L'équipe E-Learning Platform
    """
    
    try:
        send_mail(
            subject=subject,
            message=text_message,
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Error sending suspension email: {str(e)}")
        return False