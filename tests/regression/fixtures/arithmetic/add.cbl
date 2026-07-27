       IDENTIFICATION DIVISION.
       PROGRAM-ID. ADD-TEST.
       
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  NUM-A       PIC 9(4) VALUE 10.
       01  NUM-B       PIC 9(4) VALUE 20.
       
       PROCEDURE DIVISION.
       MAIN-PARA.
           ADD NUM-A TO NUM-B.
           DISPLAY NUM-B.
           STOP RUN.
