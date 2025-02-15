# Smart Mail Mentor Project Structure

**Manifest.json**     : The file contains the chrome extension configuration information

**ui.html**           : A HTML Front page which defines the structure of user intercation feilds

**ui_intractions.js** : The JavaScript file which is responsible in extracting the meaningful information and process them to backend
Also file is responsible to display the reports or inspect the insights from backend to html page

**styles.css**        : The CSS file showcasing the UI in appealing way 

**client secret.json**: The File will be hidden concering the security reasons and cannot be visible in the github

**background.js**     : The file is used to communicate with Gmail API and extract emails

**nlp.py**            : The core of the project and the file is reposnible to process and extract meaningful information for the project
