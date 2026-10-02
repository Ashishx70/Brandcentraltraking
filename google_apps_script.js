/**
 * ==============================================================================
 * BRANDCENTRAL TRACKING - GOOGLE DRIVE IMAGE UPLOAD & AUTO-CLEANUP SCRIPT
 * ==============================================================================
 * 
 * SETUP INSTRUCTIONS (2 MINUTE GUIDE):
 * ------------------------------------------------------------------------------
 * 1. Google Drive (https://drive.google.com) me ek Naya Folder banayein:
 *    Folder ka naam rakhein: "Courier_Tracking_Screenshots"
 * 
 * 2. Us folder ko open karein aur browser ke URL se FOLDER ID copy karein:
 *    Example URL: https://drive.google.com/drive/folders/1aBcDeFgHiJkLmNoPqRsTuVwXyZ
 *    Isme Folder ID hai: 1aBcDeFgHiJkLmNoPqRsTuVwXyZ
 * 
 * 3. https://script.google.com par jayein -> Click "+ New project".
 * 
 * 4. Neeche diya gaya poora code wahan paste karein.
 * 
 * 5. Neeche line 26 me FOLDER_ID ki jagah apna Folder ID daal dein:
 *    const FOLDER_ID = "YOUR_FOLDER_ID_HERE";
 * 
 * 6. Top Right me "Deploy" button dabayein -> "New deployment":
 *    - Select type (gear icon): "Web app"
 *    - Description: "Courier Tracking Image Uploader"
 *    - Execute as: "Me (your_email@gmail.com)"
 *    - Who has access: "Anyone" (Zaroori: Anyone select karein!)
 *    - Click "Deploy".
 * 
 * 7. Deploy hone ke baad jo "Web app URL" milega:
 *    (Jaise: https://script.google.com/macros/s/AKfycb.../exec)
 *    Wo Web App URL copy karke chat me bhej dein!
 * 
 * 8. Automatic 12-Hour Cleanup Trigger:
 *    Editor me function dropdown se "setupAutoDeleteTrigger" select karein aur
 *    "Run" par click karein (ek baar run karne par trigger auto-set ho jayega).
 * ==============================================================================
 */

// 🌐 CURRENT ACTIVE WEB APP URL:
// https://script.google.com/macros/s/AKfycbwlW6x8Kf_xVg2-jJKbpZlQMR8tmp6aqB50k32JmpUSxDerUgW3cGNhBW_AESRYvC-8jg/exec

// 👉 APNA GOOGLE DRIVE FOLDER ID YAHAN ENTER KAREIN:
const FOLDER_ID = "1WaKXHg25T2HpmHjOwJCYR29dD9k_MA3k";

// 12 Hours in Milliseconds (12 * 60 * 60 * 1000)
const EXPIRATION_MS = 12 * 60 * 60 * 1000;

/**
 * HTTP POST Handler - Receives Base64 High-Quality JPEG and Saves in Google Drive
 */
function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return responseJSON({ status: "error", message: "No payload received" }, 400);
    }

    const payload = JSON.parse(e.postData.contents);
    const fileName = payload.filename || ("screenshot_" + Date.now() + ".jpg");
    const base64Data = payload.image_base64;
    const mimeType = payload.mime_type || "image/jpeg";

    if (!base64Data) {
      return responseJSON({ status: "error", message: "image_base64 is required" }, 400);
    }

    // Get Drive Folder
    const folder = DriveApp.getFolderById(FOLDER_ID);
    if (!folder) {
      return responseJSON({ status: "error", message: "Folder not found. Check FOLDER_ID." }, 404);
    }

    // Decode Base64 to Blob
    const decodedBytes = Utilities.base64Decode(base64Data);
    const blob = Utilities.newBlob(decodedBytes, mimeType, fileName);

    // Create File in Google Drive
    const file = folder.createFile(blob);

    // Make viewable to anyone with the link
    file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);

    const fileId = file.getId();
    
    // High-performance direct view link that loads everywhere (browser & Excel)
    const directViewUrl = "https://drive.google.com/file/d/" + fileId + "/view?usp=sharing";
    const directThumbnailUrl = "https://lh3.googleusercontent.com/d/" + fileId;

    return responseJSON({
      status: "success",
      file_id: fileId,
      url: directViewUrl,
      thumbnail_url: directThumbnailUrl,
      file_name: fileName
    });

  } catch (error) {
    return responseJSON({
      status: "error",
      message: error.toString()
    }, 500);
  }
}

/**
 * Helper to return JSON Response with CORS headers
 */
function responseJSON(data, statusCode) {
  return ContentService.createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}

/**
 * ⏰ AUTOMATIC CLEANUP: Deletes files older than 12 hours from the folder
 */
function cleanupOldScreenshots() {
  try {
    const folder = DriveApp.getFolderById(FOLDER_ID);
    const files = folder.getFiles();
    const cutoffTime = new Date(Date.now() - EXPIRATION_MS);
    let deletedCount = 0;

    while (files.hasNext()) {
      const file = files.next();
      if (file.getDateCreated() < cutoffTime) {
        file.setTrashed(true); // Move to trash to keep drive empty
        deletedCount++;
      }
    }
    Logger.log("Cleanup completed. Deleted " + deletedCount + " old files.");
  } catch (e) {
    Logger.log("Cleanup error: " + e.toString());
  }
}

/**
 * ⚡ ONE-CLICK TRIGGER SETUP: Run this function once in Apps Script editor!
 * Automatically schedules 'cleanupOldScreenshots' to run every 1 hour.
 */
function setupAutoDeleteTrigger() {
  // Delete existing triggers for this function to avoid duplicates
  const triggers = ScriptApp.getProjectTriggers();
  for (let i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === "cleanupOldScreenshots") {
      ScriptApp.deleteTrigger(triggers[i]);
    }
  }

  // Create new hourly trigger
  ScriptApp.newTrigger("cleanupOldScreenshots")
    .timeBased()
    .everyHours(1)
    .create();

  Logger.log("Success! Automatic 12-hour cleanup trigger is now ACTIVE (runs every 1 hour).");
}
