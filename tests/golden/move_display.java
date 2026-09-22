public class MoveDisplay {

    private String msg;

    public static void main(String[] args) {
        new MoveDisplay().run();
    }

    public void run() {

        msg = "TESTING";
        System.out.println(String.format("%-20s", msg));
        return;

    }

}
